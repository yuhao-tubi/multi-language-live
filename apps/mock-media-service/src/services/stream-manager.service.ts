import { Server, Socket } from 'socket.io';
import { FragmentProvider } from './fragment-provider.service';
import { FragmentDelivery } from '../types';

export class StreamManager {
  private subscriptions: Map<string, Set<string>> = new Map(); // streamId -> Set of socketIds
  private socketStreams: Map<string, Set<string>> = new Map(); // socketId -> Set of streamIds
  private pendingAcks: Map<string, NodeJS.Timeout> = new Map(); // fragmentId -> timeout
  private retryCount: Map<string, number> = new Map(); // fragmentId -> retry count
  
  private readonly ackTimeout: number;
  private readonly maxRetries: number;

  constructor(
    private io: Server,
    private fragmentProvider: FragmentProvider,
    ackTimeout: number = 5000,
    maxRetries: number = 3
  ) {
    this.ackTimeout = ackTimeout;
    this.maxRetries = maxRetries;
    this.setupFragmentListener();
  }

  private setupFragmentListener(): void {
    this.fragmentProvider.on('fragment', (streamId: string, delivery: FragmentDelivery) => {
      this.broadcastFragment(streamId, delivery);
    });

    this.fragmentProvider.on('stream:complete', (streamId: string) => {
      this.handleStreamComplete(streamId);
    });

    this.fragmentProvider.on('stream:error', (streamId: string, error: Error) => {
      this.io.to(streamId).emit('error', {
        streamId,
        message: error.message
      });
    });
  }

  async subscribe(socket: Socket, streamId: string): Promise<void> {
    try {
      // Check if stream exists
      const availableStreams = await this.fragmentProvider.getAvailableStreams();
      if (!availableStreams.includes(streamId)) {
        socket.emit('error', {
          message: `Stream ${streamId} not found`,
          availableStreams
        });
        return;
      }

      // Add socket to room
      await socket.join(streamId);

      // Track subscription
      if (!this.subscriptions.has(streamId)) {
        this.subscriptions.set(streamId, new Set());
      }
      this.subscriptions.get(streamId)!.add(socket.id);

      if (!this.socketStreams.has(socket.id)) {
        this.socketStreams.set(socket.id, new Set());
      }
      this.socketStreams.get(socket.id)!.add(streamId);

      console.log(`Socket ${socket.id} subscribed to stream ${streamId}`);

      // Start stream if not already active
      if (!this.fragmentProvider.isStreamActive(streamId)) {
        await this.fragmentProvider.startStream(streamId);
      }

      // Confirm subscription
      socket.emit('subscribed', { streamId });
    } catch (error) {
      console.error(`Error subscribing to stream ${streamId}:`, error);
      socket.emit('error', {
        message: `Failed to subscribe to stream ${streamId}`,
        error: error instanceof Error ? error.message : String(error)
      });
    }
  }

  async unsubscribe(socket: Socket, streamId: string): Promise<void> {
    await socket.leave(streamId);

    // Remove from tracking
    const streamSubs = this.subscriptions.get(streamId);
    if (streamSubs) {
      streamSubs.delete(socket.id);
      if (streamSubs.size === 0) {
        this.subscriptions.delete(streamId);
        // Stop stream if no more subscribers
        this.fragmentProvider.stopStream(streamId);
      }
    }

    const socketSubs = this.socketStreams.get(socket.id);
    if (socketSubs) {
      socketSubs.delete(streamId);
      if (socketSubs.size === 0) {
        this.socketStreams.delete(socket.id);
      }
    }

    console.log(`Socket ${socket.id} unsubscribed from stream ${streamId}`);
    socket.emit('unsubscribed', { streamId });
  }

  handleDisconnect(socket: Socket): void {
    const streamIds = this.socketStreams.get(socket.id);
    if (streamIds) {
      // Unsubscribe from all streams
      streamIds.forEach(streamId => {
        this.unsubscribe(socket, streamId);
      });
    }
    console.log(`Socket ${socket.id} disconnected and cleaned up`);
  }

  private broadcastFragment(streamId: string, delivery: FragmentDelivery): void {
    const subscribers = this.subscriptions.get(streamId);
    if (!subscribers || subscribers.size === 0) {
      console.log(`No subscribers for stream ${streamId}, stopping stream`);
      this.fragmentProvider.stopStream(streamId);
      return;
    }

    console.log(`Broadcasting fragment ${delivery.fragment.id} to ${subscribers.size} subscribers`);

    // Send to all subscribers in the room
    this.io.to(streamId).emit('fragment:data', {
      fragment: delivery.fragment,
      data: delivery.data
    });

    // Set up acknowledgment timeout (optional - for reliability tracking)
    this.setupAckTimeout(delivery.fragment.id);
  }

  private setupAckTimeout(fragmentId: string): void {
    const timeout = setTimeout(() => {
      const retries = this.retryCount.get(fragmentId) || 0;
      if (retries < this.maxRetries) {
        console.log(`Fragment ${fragmentId} ack timeout (retry ${retries + 1}/${this.maxRetries})`);
        this.retryCount.set(fragmentId, retries + 1);
      } else {
        console.log(`Fragment ${fragmentId} max retries reached, giving up`);
        this.retryCount.delete(fragmentId);
      }
      this.pendingAcks.delete(fragmentId);
    }, this.ackTimeout);

    this.pendingAcks.set(fragmentId, timeout);
  }

  handleAck(socket: Socket, fragmentId: string): void {
    const timeout = this.pendingAcks.get(fragmentId);
    if (timeout) {
      clearTimeout(timeout);
      this.pendingAcks.delete(fragmentId);
      this.retryCount.delete(fragmentId);
      console.log(`Fragment ${fragmentId} acknowledged by ${socket.id}`);
    }
  }

  private handleStreamComplete(streamId: string): void {
    console.log(`Stream ${streamId} completed, disconnecting all subscribers`);
    
    // Notify all subscribers that the stream is complete
    this.io.to(streamId).emit('stream:complete', { streamId });

    // Get all socket IDs in the room
    const subscribers = this.subscriptions.get(streamId);
    if (subscribers) {
      // Disconnect each socket
      subscribers.forEach(socketId => {
        const socket = this.io.sockets.sockets.get(socketId);
        if (socket) {
          console.log(`Disconnecting socket ${socketId} after stream completion`);
          socket.disconnect(true);
        }
      });
    }

    // Clean up subscriptions
    this.subscriptions.delete(streamId);
  }

  getStats(): { activeStreams: number; totalSubscribers: number } {
    let totalSubscribers = 0;
    this.subscriptions.forEach(subs => {
      totalSubscribers += subs.size;
    });

    return {
      activeStreams: this.fragmentProvider.getActiveStreamCount(),
      totalSubscribers
    };
  }
}

