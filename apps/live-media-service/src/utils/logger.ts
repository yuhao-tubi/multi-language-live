/**
 * Winston logger configuration
 */
import winston from 'winston';
import path from 'path';
import fs from 'fs-extra';

const { combine, timestamp, printf, colorize, json, errors } = winston.format;

/**
 * Allowed modules for logging (populated from config)
 */
let allowedModules: Set<string> | null = null;

/**
 * Safe JSON stringify that handles circular references and errors
 */
function safeStringify(obj: any, indent: number = 2): string {
  const seen = new WeakSet();
  
  return JSON.stringify(obj, (_key, value) => {
    // Handle null and undefined
    if (value === null || value === undefined) {
      return value;
    }
    
    // Handle Error objects specially
    if (value instanceof Error) {
      const errorObj: Record<string, any> = {
        name: value.name,
        message: value.message,
        stack: value.stack,
      };
      if (value.cause) {
        errorObj.cause = value.cause;
      }
      return errorObj;
    }
    
    // Handle objects (but not primitives)
    if (typeof value === 'object') {
      // Check for circular reference
      if (seen.has(value)) {
        return '[Circular]';
      }
      seen.add(value);
    }
    
    return value;
  }, indent);
}

/**
 * Custom filter format to filter logs by module context
 */
const moduleFilter = winston.format((info) => {
  // If no filter is set, allow all logs
  if (!allowedModules || allowedModules.size === 0) {
    return info;
  }

  // If context is set and not in allowed modules, filter it out
  if (typeof info.context === 'string' && !allowedModules.has(info.context)) {
    return false;
  }

  // If no context is set (root logger), allow it
  return info;
});

/**
 * Custom log format for console output
 */
const consoleFormat = printf(({ level, message, timestamp, context, ...meta }) => {
  const contextStr = context ? `[${context}]` : '';
  const metaStr = Object.keys(meta).length ? safeStringify(meta, 2) : '';
  return `${timestamp} [${level}]${contextStr}: ${message} ${metaStr}`;
});

/**
 * Create logger instance
 */
export function createLogger(options: {
  level: string;
  format: 'json' | 'simple';
  toFile: boolean;
  toConsole: boolean;
  logsPath: string;
  moduleFilter?: string[];
}): winston.Logger {
  const transports: winston.transport[] = [];

  // Set up module filtering
  if (options.moduleFilter && options.moduleFilter.length > 0) {
    allowedModules = new Set(options.moduleFilter);
  } else {
    allowedModules = null; // Allow all modules
  }

  // Console transport
  if (options.toConsole) {
    transports.push(
      new winston.transports.Console({
        format: combine(
          moduleFilter(),
          colorize(),
          timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
          errors({ stack: true }),
          consoleFormat
        ),
      })
    );
  }

  // File transport
  if (options.toFile) {
    // Ensure logs directory exists
    fs.ensureDirSync(options.logsPath);

    // Error log file
    transports.push(
      new winston.transports.File({
        filename: path.join(options.logsPath, 'error.log'),
        level: 'error',
        format: combine(
          moduleFilter(),
          timestamp(),
          errors({ stack: true }),
          json()
        ),
      })
    );

    // Combined log file
    transports.push(
      new winston.transports.File({
        filename: path.join(options.logsPath, 'combined.log'),
        format: combine(
          moduleFilter(),
          timestamp(),
          errors({ stack: true }),
          options.format === 'json' ? json() : consoleFormat
        ),
      })
    );
  }

  const logger = winston.createLogger({
    level: options.level,
    transports,
    exitOnError: false,
  });

  return logger;
}

/**
 * Default logger instance (will be initialized in main.ts)
 */
let loggerInstance: winston.Logger | null = null;

/**
 * Initialize the default logger
 */
export function initLogger(config: {
  level: string;
  format: 'json' | 'simple';
  toFile: boolean;
  toConsole: boolean;
  logsPath: string;
  moduleFilter?: string[];
}): void {
  loggerInstance = createLogger(config);
  
  // Log which modules are being filtered
  if (config.moduleFilter && config.moduleFilter.length > 0) {
    loggerInstance.info(`📋 Log filtering enabled for modules: ${config.moduleFilter.join(', ')}`);
  } else {
    loggerInstance.info('📋 Log filtering disabled - showing all modules');
  }
}

/**
 * Get the logger instance
 * @throws Error if logger not initialized
 */
export function getLogger(): winston.Logger {
  if (!loggerInstance) {
    throw new Error('Logger not initialized. Call initLogger() first.');
  }
  return loggerInstance;
}

/**
 * Create a child logger with context
 */
export function createChildLogger(context: string): winston.Logger {
  const logger = getLogger();
  return logger.child({ context });
}

