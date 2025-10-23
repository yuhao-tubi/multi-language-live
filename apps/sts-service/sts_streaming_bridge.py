#!/usr/bin/env python3
"""
STS to Streaming-Demux-Remux Bridge

This service bridges the STS (Speech-to-Speech) processing pipeline with the
streaming-demux-remux service for web-based audio playback.

It receives processed audio fragments from the STS service and forwards them
to streaming-demux-remux for HLS streaming and web playback.

Author: Philip Baillargeon (Assistance by Cursor/GPT)
"""

import socketio
import requests
import json
import time
import argparse
from pathlib import Path
from typing import Dict, Any, Optional
import threading
import queue

class STSStreamingBridge:
    def __init__(self, 
                 sts_server_url: str = "ws://localhost:4000",
                 demux_api_url: str = "http://localhost:3000",
                 stream_id: str = "stream-1",
                 targets: str = "es"):
        
        self.sts_server_url = sts_server_url
        self.demux_api_url = demux_api_url
        self.stream_id = stream_id
        self.targets = [t.strip() for t in targets.split(",") if t.strip()]
        
        # Socket.IO client for STS service
        self.sts_client = socketio.Client()
        self.connected = False
        self.subscribed = False
        
        # Processing state
        self.running = False
        self.fragment_count = 0
        self.processed_count = 0
        
        # Audio fragment queue for streaming-demux-remux
        self.audio_queue = queue.Queue()
        self.streaming_thread = None
        
        self.setup_sts_handlers()
        
    def setup_sts_handlers(self):
        """Setup Socket.IO event handlers for STS service"""
        @self.sts_client.event
        def connect():
            print(f"✓ Connected to STS service: {self.sts_server_url}")
            print(f"Socket ID: {self.sts_client.sid}")
            
        @self.sts_client.event
        def disconnect():
            print("✓ Disconnected from STS service")
            
        @self.sts_client.event
        def subscribed(data):
            print(f"✓ Successfully subscribed to stream: {data['streamId']}")
            
        @self.sts_client.on('fragment:processed')
        def fragment_processed(data):
            self.handle_processed_fragment(data)
            
        @self.sts_client.on('stream:complete')
        def stream_complete(data):
            print(f"✓ Stream completed: {data['streamId']}")
            print(f"Total fragments processed: {self.processed_count}")
            
        @self.sts_client.on('error')
        def error(data):
            print(f"ERROR: {data}")
            
    def handle_processed_fragment(self, data):
        """Handle processed fragment from STS service"""
        fragment = data['fragment']
        audio_data = data['data']
        
        self.fragment_count += 1
        print(f"\n📦 Processed Fragment {self.fragment_count} Received:")
        print(f"  ID: {fragment['id']}")
        print(f"  Sequence: {fragment['sequenceNumber']}")
        print(f"  Size: {len(audio_data):,} bytes ({len(audio_data)/1024:.2f} KB)")
        
        # Add to queue for streaming-demux-remux
        self.audio_queue.put({
            'fragment': fragment,
            'audio_data': audio_data,
            'timestamp': time.time()
        })
        
        self.processed_count += 1
        
    def start_streaming_thread(self):
        """Start thread to send audio to streaming-demux-remux"""
        if self.streaming_thread and self.streaming_thread.is_alive():
            return
            
        self.streaming_thread = threading.Thread(target=self._streaming_worker, daemon=True)
        self.streaming_thread.start()
        print("✓ Started streaming thread")
        
    def _streaming_worker(self):
        """Worker thread to send audio fragments to streaming-demux-remux"""
        print("🔄 Streaming worker started")
        
        while self.running:
            try:
                # Get fragment from queue with timeout
                item = self.audio_queue.get(timeout=1.0)
                
                fragment = item['fragment']
                audio_data = item['audio_data']
                
                print(f"📤 Sending fragment {fragment['sequenceNumber']} to streaming-demux-remux...")
                
                # Send to streaming-demux-remux
                success = self._send_to_demux(fragment, audio_data)
                
                if success:
                    print(f"✓ Fragment {fragment['sequenceNumber']} sent successfully")
                else:
                    print(f"✗ Failed to send fragment {fragment['sequenceNumber']}")
                    
                self.audio_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"ERROR in streaming worker: {e}")
                
        print("🔄 Streaming worker stopped")
        
    def _send_to_demux(self, fragment: Dict[str, Any], audio_data: bytes) -> bool:
        """Send audio fragment to streaming-demux-remux"""
        try:
            # Prepare the data for streaming-demux-remux
            payload = {
                'fragment_id': fragment['id'],
                'sequence_number': fragment['sequenceNumber'],
                'timestamp': fragment['timestamp'],
                'duration': fragment['duration'],
                'codec': fragment['codec'],
                'sample_rate': fragment['sampleRate'],
                'channels': fragment['channels'],
                'audio_data': audio_data.hex()  # Convert bytes to hex string for JSON
            }
            
            # Send to streaming-demux-remux API
            response = requests.post(
                f"{self.demux_api_url}/api/audio-fragment",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                return True
            else:
                print(f"  HTTP {response.status_code}: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"  Request error: {e}")
            return False
        except Exception as e:
            print(f"  Error: {e}")
            return False
            
    def check_demux_service(self) -> bool:
        """Check if streaming-demux-remux service is available"""
        try:
            response = requests.get(f"{self.demux_api_url}/api/status", timeout=5)
            if response.status_code == 200:
                data = response.json()
                print(f"✓ Streaming-demux-remux service is running")
                print(f"  Status: {data.get('status', 'unknown')}")
                return True
            else:
                print(f"✗ Streaming-demux-remux service returned HTTP {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"✗ Cannot connect to streaming-demux-remux service: {e}")
            return False
            
    def run(self):
        """Run the bridge service"""
        print("=" * 60)
        print("STS to Streaming-Demux-Remux Bridge")
        print("=" * 60)
        print(f"STS Server: {self.sts_server_url}")
        print(f"Demux API: {self.demux_api_url}")
        print(f"Stream ID: {self.stream_id}")
        print(f"Target languages: {', '.join(self.targets)}")
        print("=" * 60)
        
        # Check if streaming-demux-remux is available
        if not self.check_demux_service():
            print("ERROR: Streaming-demux-remux service is not available")
            print("Please start it with: npx nx serve streaming-demux-remux")
            return
            
        try:
            print(f"Connecting to STS service...")
            self.sts_client.connect(self.sts_server_url)
            
            print(f"→ Subscribing to stream: {self.stream_id}")
            self.sts_client.emit('subscribe', {'streamId': self.stream_id})
            
            # Start streaming thread
            self.running = True
            self.start_streaming_thread()
            
            print("Waiting for processed fragments...")
            print("Press Ctrl+C to stop")
            
            # Keep the connection alive
            while True:
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n\nStopping bridge service...")
        except Exception as e:
            print(f"ERROR: {e}")
        finally:
            self.running = False
            if self.sts_client.connected:
                self.sts_client.disconnect()
            print("✓ Bridge service stopped")

def main():
    parser = argparse.ArgumentParser(description='Bridge STS service with streaming-demux-remux')
    parser.add_argument('--sts-server', default='ws://localhost:4000',
                       help='STS service WebSocket URL')
    parser.add_argument('--demux-api', default='http://localhost:3000',
                       help='Streaming-demux-remux API URL')
    parser.add_argument('--stream-id', default='stream-1',
                       help='Stream ID to subscribe to')
    parser.add_argument('--targets', default='es',
                       help='Target languages (comma-separated)')
    
    args = parser.parse_args()
    
    bridge = STSStreamingBridge(
        sts_server_url=args.sts_server,
        demux_api_url=args.demux_api,
        stream_id=args.stream_id,
        targets=args.targets
    )
    
    bridge.run()

if __name__ == "__main__":
    main()
