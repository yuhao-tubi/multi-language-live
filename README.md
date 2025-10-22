# Multi-Language Live Streaming Monorepo

This is an Nx-powered monorepo for multi-language live streaming projects.

## Structure

```
multi-language-live/
├── apps/
│   └── streaming-demux-remux/    # HLS audio manipulation pipeline with SRS integration
├── libs/                          # Shared libraries (future)
├── nx.json                        # Nx configuration
├── tsconfig.base.json             # Base TypeScript configuration
└── package.json                   # Root package.json with Nx scripts
```

## Getting Started

### Prerequisites

- Node.js (v18+)
- npm or yarn
- FFmpeg (for streaming-demux-remux app)
- Docker (for SRS server in streaming-demux-remux app)

### Installation

```bash
# Install dependencies
npm install

# Install app-specific dependencies
cd apps/streaming-demux-remux && npm install
```

## Available Commands

### Monorepo Commands

```bash
# Build all projects
npm run build

# Build specific app
nx build streaming-demux-remux

# Run dev server for streaming-demux-remux
npm run dev
# or
nx dev streaming-demux-remux

# Start production build
npm run start
# or
nx start streaming-demux-remux
```

### App-Specific Commands

For the `streaming-demux-remux` app:

```bash
# Check TypeScript without emitting
nx check streaming-demux-remux

# Verify setup
nx verify streaming-demux-remux

# SRS server management
nx srs:start streaming-demux-remux
nx srs:stop streaming-demux-remux
nx srs:restart streaming-demux-remux
nx srs:logs streaming-demux-remux
nx srs:remove streaming-demux-remux
```

## Apps

### streaming-demux-remux

Multi-process HLS audio manipulation pipeline with SRS integration.

**Location:** `apps/streaming-demux-remux/`

**Documentation:**
- [README](apps/streaming-demux-remux/README.md)
- [Quick Start](apps/streaming-demux-remux/QUICKSTART.md)
- [Implementation Summary](apps/streaming-demux-remux/IMPLEMENTATION_SUMMARY.md)

## Nx Workspace

This monorepo uses [Nx](https://nx.dev) for:
- Task orchestration and caching
- Dependency graph management
- Code generation and scaffolding
- Consistent tooling across projects

### Useful Nx Commands

```bash
# Show project graph
npx nx graph

# Run affected commands (only changed projects)
npx nx affected:build
npx nx affected:test

# Clear cache
npx nx reset
```

## Adding New Projects

To add a new app:

```bash
# Generate a new app
npx nx g @nx/node:app my-new-app

# Or manually create in apps/ directory with project.json
```

To add a new library:

```bash
# Generate a new library
npx nx g @nx/js:lib my-new-lib
```

## Contributing

When adding new apps or libraries:
1. Follow the existing project structure
2. Add a `project.json` with appropriate targets
3. Update this README with relevant information
4. Ensure all tests pass before committing

## License

ISC

