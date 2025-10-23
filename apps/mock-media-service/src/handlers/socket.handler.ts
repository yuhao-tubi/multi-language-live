import { Socket } from 'socket.io';
import { StreamManager } from '../services/stream-manager.service';
import { MediaOutputService } from '../services/media-output.service';

export function setupSocketHandlers(socket: Socket, streamManager: StreamManager, mediaOutput?: MediaOutputService): void {
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
  socket.on('fragment:processed', async (delivery: { fragment: any; data: Buffer }) => {
    const { fragment, data } = delivery;
    if (!fragment?.id || !data) {
      socket.emit('error', { message: 'fragment and data are required' });
      return;
    }
    try {
      if (mediaOutput) {
        const savedPath = await mediaOutput.saveProcessedFragment(fragment, data);
        console.log(`Saved processed fragment ${fragment.id} to ${savedPath}`);
      }
      console.log(`Received processed fragment ${fragment.id} from ${socket.id}, size: ${data.length} bytes`);
    } catch (e) {
      socket.emit('error', { message: 'Failed to save processed fragment', error: e instanceof Error ? e.message : String(e) });
    }
  });

  // Handle stream remux
  socket.on('stream:remux', async (data: { streamId: string }) => {
    const { streamId } = data || {} as any;
    if (!streamId) {
      socket.emit('error', { message: 'streamId is required' });
      return;
    }
    if (!mediaOutput) {
      socket.emit('error', { message: 'Media output service unavailable' });
      return;
    }
    try {
      const { outputVideoPath } = await mediaOutput.remuxStream(streamId);
      socket.emit('stream:remux:complete', { streamId, outputVideo: outputVideoPath });
    } catch (e) {
      socket.emit('error', { message: 'Remux failed', streamId, error: e instanceof Error ? e.message : String(e) });
    }
  });

  // Handle output clean
  socket.on('output:clean', async (data: { streamId?: string } = {}) => {
    if (!mediaOutput) {
      socket.emit('error', { message: 'Media output service unavailable' });
      return;
    }
    try {
      const removed = await mediaOutput.cleanOutput(data.streamId);
      socket.emit('output:clean:complete', { removed });
    } catch (e) {
      socket.emit('error', { message: 'Cleanup failed', error: e instanceof Error ? e.message : String(e) });
    }
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

