/**
 * Type declarations for modules without official TypeScript types
 */

declare module 'm3u8-parser' {
  export default class Parser {
    manifest: {
      playlists?: Array<{
        uri: string;
        attributes?: {
          BANDWIDTH?: number;
          RESOLUTION?: {
            width: number;
            height: number;
          };
          [key: string]: any;
        };
      }>;
      segments?: Array<{
        uri: string;
        duration: number;
        [key: string]: any;
      }>;
      [key: string]: any;
    };
    
    push(chunk: string): void;
    end(): void;
  }
}

declare module 'm3u8stream' {
  import { Readable } from 'stream';
  
  interface M3U8StreamOptions {
    begin?: string | number | Date;
    liveBuffer?: number;
    chunkReadahead?: number;
    highWaterMark?: number;
    requestOptions?: any;
    parser?: 'dash-mpd' | 'hls' | 'm3u8';
    id?: string;
  }
  
  function m3u8stream(url: string, options?: M3U8StreamOptions): Readable;
  
  export = m3u8stream;
}

