# Migration to Nx Monorepo

This document describes the migration from the previous structure to the Nx monorepo.

## What Changed

### Directory Structure

**Before:**
```
multi-language-live/
├── demo/
│   └── streaming-demux-remux/
└── package.json
```

**After:**
```
multi-language-live/
├── apps/
│   └── streaming-demux-remux/    # Moved from demo/
├── libs/                          # For future shared libraries
├── nx.json                        # Nx configuration
├── tsconfig.base.json             # Base TypeScript config
└── package.json                   # Root package.json
```

### Configuration Files

#### New Files
- `nx.json` - Nx workspace configuration
- `tsconfig.base.json` - Base TypeScript configuration for the monorepo
- `apps/streaming-demux-remux/project.json` - Nx project configuration with build targets
- `.gitignore` - Updated to include Nx cache directories

#### Modified Files
- `package.json` - Updated with Nx scripts and marked as private
- `README.md` - New root README with monorepo documentation

### Command Changes

#### Before

```bash
cd demo/streaming-demux-remux
npm run build
npm run dev
npm run start
```

#### After

**From root:**
```bash
# Using npm scripts
npm run build
npm run dev
npm run start

# Using Nx directly
npx nx build streaming-demux-remux
npx nx dev streaming-demux-remux
npx nx start streaming-demux-remux
```

**From app directory:**
```bash
cd apps/streaming-demux-remux
npm run build
npm run dev
npm run start
```

### All Available Commands

#### Monorepo-level Commands

```bash
# Build all projects
npm run build

# Run dev for streaming-demux-remux
npm run dev

# Start production server
npm run start

# Test all projects
npm run test
```

#### App-specific Commands (via Nx)

```bash
# Build
npx nx build streaming-demux-remux

# Dev server
npx nx dev streaming-demux-remux

# Production start
npx nx start streaming-demux-remux

# TypeScript check
npx nx check streaming-demux-remux

# Verify setup
npx nx verify streaming-demux-remux

# SRS server management
npx nx srs:start streaming-demux-remux
npx nx srs:stop streaming-demux-remux
npx nx srs:restart streaming-demux-remux
npx nx srs:logs streaming-demux-remux
npx nx srs:remove streaming-demux-remux
```

## Benefits of the New Structure

### 1. Scalability
- Easy to add new apps and libraries
- Shared code can be extracted into libraries
- Consistent project structure across all apps

### 2. Build Performance
- Nx caches build outputs
- Only rebuilds what changed
- Parallel execution of independent tasks

### 3. Dependency Management
- Clear dependency graph between projects
- Nx ensures correct build order
- Prevents circular dependencies

### 4. Developer Experience
- Consistent commands across all projects
- Built-in code generators for new projects
- Visual project graph (`npx nx graph`)

### 5. Code Quality
- Easier to enforce coding standards across projects
- Shared configurations (tsconfig, eslint, etc.)
- Linting rules can target affected projects only

## Future Enhancements

### Potential Additions

1. **Shared Libraries**
   ```
   libs/
   ├── shared-utils/       # Common utilities
   ├── audio-processing/   # Shared audio processing logic
   └── streaming-common/   # Common streaming functionality
   ```

2. **More Apps**
   - Additional streaming applications
   - Admin dashboards
   - API services

3. **Enhanced Nx Features**
   - Code generation templates
   - Custom executors for specialized build tasks
   - Integrated testing with Nx affected commands

### Migration Steps for New Apps

To add a new application:

1. Create directory in `apps/`
2. Add `project.json` with targets
3. Add app-specific `package.json` and `tsconfig.json`
4. Update root `README.md`

Or use Nx generators:
```bash
npx nx g @nx/node:app my-new-app
```

## Rollback (if needed)

If you need to revert to the old structure:

1. Copy `apps/streaming-demux-remux` back to `demo/streaming-demux-remux`
2. Restore the old root `package.json`
3. Remove `nx.json`, `tsconfig.base.json`
4. Remove Nx dependencies from `package.json`
5. Run `npm install`

## Questions?

- Check the [Nx documentation](https://nx.dev)
- See the root [README.md](README.md)
- Review the app-specific [README](apps/streaming-demux-remux/README.md)

