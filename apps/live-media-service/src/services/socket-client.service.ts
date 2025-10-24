/**
 * Socket client service for communicating with audio processor
 */
import { io, Socket } from 'socket.io-client';
import { EventEmitter } from 'events';
import {
  FragmentMetadata,
  FragmentDataEvent,
  FragmentProcessedEvent,
  FragmentErrorEvent,
} from '../types/protocol.js';
import { getLogger } from '../utils/logger.js';

let logger: ReturnType<typeof getLogger> | null = null;

/**
 * Socket client configuration
 */
export interface SocketClientConfig {
  /** Audio processor server URL */
  serverUrl: string;
  /** Reconnection attempts */
  reconnectAttempts?: number;
  /** Reconnection delay in milliseconds */
  reconnectDelayMs?: number;
}

/**
 * Socket client events
 */
export interface SocketClientEvents {
  'fragment:processed': (event: FragmentProcessedEvent) => void;
  'fragment:error': (event: FragmentErrorEvent) => void;
  'connected': () => void;
  'disconnected': () => void;
  'error': (error: Error) => void;
}

/**
 * Socket client for audio processor communication
 */
export class SocketClientService extends EventEmitter {
  private config: SocketClientConfig;
  private socket: Socket | null = null;
  private isConnected: boolean = false;

  constructor(config: SocketClientConfig) {
    super();
    this.config = config;

    // Lazy initialize logger
    if (!logger) {
      try {
        logger = getLogger().child({ context: 'SocketClientService' });
      } catch {
        logger = null;
      }
    }

    this.log('info', `SocketClientService initialized for: ${config.serverUrl}`);
  }

  private log(level: 'debug' | 'info' | 'warn' | 'error', message: string, ...args: unknown[]): void {
    if (logger) {
      logger[level](message, ...args);
    }
  }

  /**
   * Connect to audio processor server
   */
  async connect(): Promise<void> {
    if (this.isConnected) {
      this.log('warn', 'Already connected');
      return;
    }

    this.log('info', `Connecting to audio processor: ${this.config.serverUrl}`);

    this.socket = io(this.config.serverUrl, {
      reconnection: true,
      reconnectionAttempts: this.config.reconnectAttempts || 5,
      reconnectionDelay: this.config.reconnectDelayMs || 2000,
      transports: ['websocket'],
    });

    // Set up event handlers
    this.setupEventHandlers();

    // Wait for connection
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Connection timeout'));
      }, 10000);

      this.socket?.once('connect', () => {
        clearTimeout(timeout);
        this.isConnected = true;
        this.log('info', 'Connected to audio processor');
        this.emit('connected');
        resolve();
      });

      this.socket?.once('connect_error', (error) => {
        clearTimeout(timeout);
        this.log('error', 'Connection error:', error);
        reject(error);
      });
    });
  }

  /**
   * Disconnect from audio processor server
   */
  disconnect(): void {
    if (!this.socket) {
      return;
    }

    this.log('info', 'Disconnecting from audio processor');
    this.socket.disconnect();
    this.socket = null;
    this.isConnected = false;
  }

  /**
   * Send fragment for processing
   */
  async sendFragment(fragment: FragmentMetadata, data: Buffer): Promise<void> {
    if (!this.socket || !this.isConnected) {
      throw new Error('Not connected to audio processor');
    }

    this.log('debug', `Sending fragment: ${fragment.id}`);

    const event: FragmentDataEvent = {
      fragment,
      data,
    };

    this.socket.emit('fragment:data', event);

    this.log('info', `Sent fragment ${fragment.id} (${(data.length / 1024).toFixed(2)} KB)`);
  }

  /**
   * Set up socket event handlers
   */
  private setupEventHandlers(): void {
    if (!this.socket) {
      return;
    }

    // Connection events
    this.socket.on('connect', () => {
      this.isConnected = true;
      this.log('info', 'Connected to audio processor');
      this.emit('connected');
    });

    this.socket.on('disconnect', () => {
      this.isConnected = false;
      this.log('warn', 'Disconnected from audio processor');
      this.emit('disconnected');
    });

    this.socket.on('error', (error) => {
      this.log('error', 'Socket error:', error);
      this.emit('error', error);
    });

    // Fragment events
    this.socket.on('fragment:processed', (event: FragmentProcessedEvent) => {
      this.log('info', `Received processed fragment: ${event.fragment.id}`);
      this.emit('fragment:processed', event);
    });

    this.socket.on('fragment:error', (event: FragmentErrorEvent) => {
      this.log('error', `Fragment error: ${event.fragment.id} - ${event.error}`);
      this.emit('fragment:error', event);
    });
  }

  /**
   * Get connection status
   */
  getStatus(): {
    isConnected: boolean;
    serverUrl: string;
  } {
    return {
      isConnected: this.isConnected,
      serverUrl: this.config.serverUrl,
    };
  }

  // Typed event emitter methods
  on<K extends keyof SocketClientEvents>(
    event: K,
    listener: SocketClientEvents[K]
  ): this {
    return super.on(event, listener);
  }

  emit<K extends keyof SocketClientEvents>(
    event: K,
    ...args: Parameters<SocketClientEvents[K]>
  ): boolean {
    return super.emit(event, ...args);
  }
}

