# Quick Start Guide

## Installation

```bash
# Install root dependencies
npm install

# Install app dependencies
cd apps/streaming-demux-remux
npm install
cd ../..
```

## Common Commands

### Build

```bash
# Build all projects
npm run build

# Build specific app
npx nx build streaming-demux-remux
```

### Development

```bash
# Run dev server for streaming-demux-remux
npm run dev

# Or use Nx directly
npx nx dev streaming-demux-remux
```

### Production

```bash
# Start production server
npm run start

# Or use Nx directly
npx nx start streaming-demux-remux
```

## Nx Commands

### Project Management

```bash
# List all projects
npx nx show projects

# Show project details
npx nx show project streaming-demux-remux

# View project graph
npx nx graph
```

### Build & Test

```bash
# Build only changed projects
npx nx affected:build

# Test only changed projects
npx nx affected:test

# Run any target
npx nx [target] [project-name]
```

### Cache Management

```bash
# Clear Nx cache
npx nx reset

# View cache status
npx nx daemon --status
```

## App-Specific Commands

### streaming-demux-remux

```bash
# TypeScript check
npx nx check streaming-demux-remux

# Verify setup
npx nx verify streaming-demux-remux

# SRS server management
npx nx srs:start streaming-demux-remux
npx nx srs:stop streaming-demux-remux
npx nx srs:restart streaming-demux-remux
npx nx srs:logs streaming-demux-remux
```

## Directory Structure

```
multi-language-live/
├── apps/                          # Applications
│   └── streaming-demux-remux/    # HLS streaming app
├── libs/                          # Shared libraries (future)
├── node_modules/                  # Root dependencies
├── nx.json                        # Nx configuration
├── tsconfig.base.json             # Base TypeScript config
└── package.json                   # Root package.json
```

## Next Steps

1. Read the [README](README.md) for detailed information
2. Check the [Migration Guide](MIGRATION.md) for what changed
3. Explore the [streaming-demux-remux app](apps/streaming-demux-remux/README.md)

## Troubleshooting

### Build fails
```bash
# Clear cache and rebuild
npx nx reset
npx nx build streaming-demux-remux
```

### Module not found
```bash
# Reinstall dependencies
cd apps/streaming-demux-remux
rm -rf node_modules package-lock.json
npm install
```

### Nx issues
```bash
# Stop Nx daemon
npx nx daemon --stop

# Restart and clear cache
npx nx reset
```

## Resources

- [Nx Documentation](https://nx.dev)
- [Project Graph](project-graph.html) (generated via `npx nx graph --file=project-graph.html`)
- [App Documentation](apps/streaming-demux-remux/README.md)

