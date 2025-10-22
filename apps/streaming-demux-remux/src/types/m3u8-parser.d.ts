declare module 'm3u8-parser' {
  export class Parser {
    constructor();
    push(data: string): void;
    end(): void;
    manifest: {
      playlists?: Array<{
        uri: string;
        attributes?: {
          RESOLUTION?: {
            width: number;
            height: number;
          };
          BANDWIDTH?: number;
        };
      }>;
      segments?: Array<{
        uri: string;
        duration: number;
      }>;
    };
  }

  export class LineStream {
    constructor();
    push(data: string): void;
    on(event: string, callback: Function): void;
  }

  export class ParseStream {
    constructor();
    push(data: string): void;
    on(event: string, callback: Function): void;
  }
}

