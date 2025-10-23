export interface AudioFragment {
  id: string;
  streamId: string;
  sequenceNumber: number;
  timestamp: number;
  duration: number;
  codec: string;
  sampleRate: number;
  channels: number;
  metadata?: Record<string, any>;
}

export interface FragmentDelivery {
  fragment: AudioFragment;
  data: Buffer;
}

export interface StreamConfig {
  fragmentDataInterval: number;
  ackTimeoutMs: number;
  maxRetries: number;
  maxFragmentsPerStream: number;
}

