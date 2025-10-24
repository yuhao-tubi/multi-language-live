/**
 * Tubi Authentication Service
 * Handles anonymous authentication and token generation
 */
import crypto from 'crypto';
import { getLogger } from '../utils/logger.js';

// Lazy-load logger to avoid initialization order issues
const getLog = () => getLogger();

const ACCOUNT_API_BASE = 'https://account.production-public.tubi.io';
const DEFAULT_PLATFORM = 'amazon';
const DEFAULT_DEVICE_ID = '5304f5df-5052-4edc-8087-c0988bd8ae10';

interface SigningKeyResponse {
  id: string;
  key: string;
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

interface TokenCache {
  accessToken: string;
  expiresAt: number;
}

// Token cache
let cachedToken: TokenCache | null = null;

/**
 * Generate a code verifier (random string)
 */
function generateCodeVerifier(): string {
  return crypto.randomBytes(32).toString('base64url');
}

/**
 * Generate a code challenge from verifier
 */
function generateCodeChallenge(verifier: string): string {
  return crypto
    .createHash('sha256')
    .update(verifier)
    .digest('base64url');
}

/**
 * Generate HMAC signature for token request
 */
function generateSignature(
  key: string,
  method: string,
  path: string,
  queryParams: Record<string, string>,
  bodyHash: string
): string {
  const sortedParams = Object.keys(queryParams)
    .sort()
    .map((k) => `${k}=${queryParams[k]}`)
    .join('&');

  const stringToSign = [
    method,
    path,
    sortedParams,
    bodyHash,
  ].join('\n');

  const decodedKey = Buffer.from(key, 'base64');
  return crypto
    .createHmac('sha256', decodedKey)
    .update(stringToSign)
    .digest('hex');
}

/**
 * Step 1: Get signing key
 */
async function getSigningKey(
  challenge: string,
  deviceId: string = DEFAULT_DEVICE_ID,
  platform: string = DEFAULT_PLATFORM
): Promise<SigningKeyResponse | null> {
  try {
    const url = `${ACCOUNT_API_BASE}/device/anonymous/signing_key`;
    const body = {
      challenge,
      version: '1.0.0',
      platform,
      device_id: deviceId,
    };

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      getLog().error(`Failed to get signing key: ${response.status} ${response.statusText}`);
      return null;
    }

    const data = await response.json();
    return data as SigningKeyResponse;
  } catch (error) {
    getLog().error('Error getting signing key:', error);
    return null;
  }
}

/**
 * Step 2: Request anonymous token
 */
async function requestAnonymousToken(
  verifier: string,
  clientId: string,
  signingKey: string,
  deviceId: string = DEFAULT_DEVICE_ID,
  platform: string = DEFAULT_PLATFORM
): Promise<TokenResponse | null> {
  try {
    const body = {
      verifier,
      id: clientId,
      platform,
      device_id: deviceId,
    };

    const bodyString = JSON.stringify(body);
    const bodyHash = crypto
      .createHash('sha256')
      .update(bodyString)
      .digest('hex');

    // Generate query parameters for signature
    const timestamp = new Date().toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
    const queryParams = {
      'X-Tubi-Algorithm': 'TUBI-HMAC-SHA256',
      'X-Tubi-Date': timestamp,
      'X-Tubi-Expires': '30',
      'X-Tubi-SignedHeaders': 'content-type',
    };

    // Generate signature
    const signature = generateSignature(
      signingKey,
      'POST',
      '/device/anonymous/token',
      queryParams,
      bodyHash
    );

    queryParams['X-Tubi-Signature'] = signature;

    // Build URL with query parameters
    const url = `${ACCOUNT_API_BASE}/device/anonymous/token?${new URLSearchParams(queryParams)}`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: bodyString,
    });

    if (!response.ok) {
      const errorText = await response.text();
      getLog().error(`Failed to get token: ${response.status} ${response.statusText}`, errorText);
      return null;
    }

    const data = await response.json();
    return data as TokenResponse;
  } catch (error) {
    getLog().error('Error requesting anonymous token:', error);
    return null;
  }
}

/**
 * Get Tubi access token (with caching)
 */
export async function getTubiAccessToken(
  deviceId: string = DEFAULT_DEVICE_ID,
  platform: string = DEFAULT_PLATFORM
): Promise<string | null> {
  // Check if we have a valid cached token
  if (cachedToken && cachedToken.expiresAt > Date.now()) {
    getLog().debug('Using cached Tubi access token');
    return cachedToken.accessToken;
  }

  getLog().info('Generating new Tubi access token');

  try {
    // Step 1: Generate code verifier and challenge
    const verifier = generateCodeVerifier();
    const challenge = generateCodeChallenge(verifier);

    // Step 2: Get signing key
    const signingKeyData = await getSigningKey(challenge, deviceId, platform);
    if (!signingKeyData) {
      getLog().error('Failed to get signing key');
      return null;
    }

    getLog().debug('Got signing key:', signingKeyData.id);

    // Step 3: Request token
    const tokenData = await requestAnonymousToken(
      verifier,
      signingKeyData.id,
      signingKeyData.key,
      deviceId,
      platform
    );

    if (!tokenData) {
      getLog().error('Failed to get access token');
      return null;
    }

    getLog().info('Successfully generated Tubi access token');

    // Cache token (expire 5 minutes before actual expiration)
    cachedToken = {
      accessToken: tokenData.access_token,
      expiresAt: Date.now() + (tokenData.expires_in - 300) * 1000,
    };

    return tokenData.access_token;
  } catch (error) {
    getLog().error('Error in getTubiAccessToken:', error);
    return null;
  }
}

/**
 * Clear cached token (useful for testing or error recovery)
 */
export function clearTubiTokenCache(): void {
  cachedToken = null;
  getLog().info('Tubi token cache cleared');
}

