import { Socket } from 'socket.io';
import { StreamManager } from '../services/stream-manager.service';

export function setupSocketHandlers(socket: Socket, streamManager: StreamManager): void {
  console.log(`Client connected: ${socket.id}`);

  // Handle subscribe event
  socket.on('subscribe', async (data: { streamId: string }) => {
    const { streamId } = data;
    if (!streamId) {
      socket.emit('error', { message: 'streamId is required' });
      return;
    }

    console.log(`Socket ${socket.id} requesting subscription to ${streamId}`);
    await streamManager.subscribe(socket, streamId);
  });

  // Handle unsubscribe event
  socket.on('unsubscribe', async (data: { streamId: string }) => {
    const { streamId } = data;
    if (!streamId) {
      socket.emit('error', { message: 'streamId is required' });
      return;
    }

    console.log(`Socket ${socket.id} unsubscribing from ${streamId}`);
    await streamManager.unsubscribe(socket, streamId);
  });

  // Handle fragment acknowledgment
  socket.on('fragment:ack', (data: { fragmentId: string }) => {
    const { fragmentId } = data;
    if (!fragmentId) {
      return;
    }

    streamManager.handleAck(socket, fragmentId);
  });

  // Handle processed fragment
  socket.on('fragment:processed', (delivery: { fragment: any; data: Buffer }) => {
    const { fragment, data } = delivery;
    if (!fragment?.id || !data) {
      socket.emit('error', { message: 'fragment and data are required' });
      return;
    }

    console.log(`Received processed fragment ${fragment.id} from ${socket.id}, size: ${data.length} bytes`);
    // Log for tracking/debugging purposes
  });

  // Handle disconnect
  socket.on('disconnect', (reason: string) => {
    console.log(`Client disconnected: ${socket.id}, reason: ${reason}`);
    streamManager.handleDisconnect(socket);
  });

  // Handle errors
  socket.on('error', (error: Error) => {
    console.error(`Socket error for ${socket.id}:`, error);
  });
}

