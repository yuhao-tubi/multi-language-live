/**
 * Tubi EPG Programming API Service
 * Handles fetching programming and manifest URLs
 */
import { getTubiAccessToken } from './tubi-auth.service.js';
import { getLogger } from '../utils/logger.js';

// Lazy-load logger to avoid initialization order issues
const getLog = () => getLogger();

const EPG_CDN_BASE = 'https://epg-cdn.production-public.tubi.io';
const DEFAULT_PLATFORM = 'amazon';
const DEFAULT_DEVICE_ID = '5304f5df-5052-4edc-8087-c0988bd8ae10';

// TypeScript interfaces matching the guide
interface ManifestInfo {
  url: string;
  duration: number;
}

interface VideoResource {
  type: string;
  manifest: ManifestInfo;
  resolution?: string;
  codec?: string;
}

interface ProgrammingRow {
  content_id: string;
  title: string;
  video_resources: VideoResource[];
  images?: {
    poster?: string[];
    background?: string[];
  };
}

interface EpgProgrammingResponse {
  rows: ProgrammingRow[];
}

export interface EpgProgrammingOptions {
  contentId: string;
  platform?: string;
  deviceId?: string;
  limitResolutions?: string[];
  lookahead?: number;
  userId?: string;
}

/**
 * Get EPG programming data with manifest URLs
 */
export async function getEpgProgramming(
  options: EpgProgrammingOptions
): Promise<EpgProgrammingResponse | null> {
  try {
    // Step 1: Get access token
    const accessToken = await getTubiAccessToken(
      options.deviceId || DEFAULT_DEVICE_ID,
      options.platform || DEFAULT_PLATFORM
    );

    if (!accessToken) {
      getLog().error('Failed to get Tubi access token');
      return null;
    }

    // Step 2: Build query parameters
    const params = new URLSearchParams({
      platform: options.platform || DEFAULT_PLATFORM,
      device_id: options.deviceId || DEFAULT_DEVICE_ID,
      content_id: options.contentId,
      lookahead: String(options.lookahead || 1),
    });

    // Add resolution limits
    if (options.limitResolutions && options.limitResolutions.length > 0) {
      options.limitResolutions.forEach((res) => {
        params.append('limit_resolutions[]', res);
      });
    } else {
      // Default resolutions
      params.append('limit_resolutions[]', 'h264_1080p');
      params.append('limit_resolutions[]', 'h265_1080p');
    }

    // Add user ID if provided
    if (options.userId) {
      params.append('user_id', options.userId);
    }

    // Step 3: Make API request
    const url = `${EPG_CDN_BASE}/content/epg/programming?${params}`;

    getLog().debug('Fetching EPG programming:', { contentId: options.contentId });

    const response = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: '*/*',
        'Accept-Language': 'en-US',
        Authorization: `Bearer ${accessToken}`,
        'User-Agent': 'live-media-service/1.0',
      },
    });

    if (!response.ok) {
      getLog().error(`EPG API error: ${response.status} ${response.statusText}`);
      const errorText = await response.text();
      getLog().error('EPG API error details:', errorText);
      return null;
    }

    const data = await response.json();
    getLog().info('Successfully fetched EPG programming:', {
      contentId: options.contentId,
      rowCount: data.rows?.length || 0,
    });

    return data as EpgProgrammingResponse;
  } catch (error) {
    getLog().error('Error calling EPG Programming API:', error);
    return null;
  }
}

/**
 * Extract manifest URL from EPG programming response
 */
export function getManifestUrl(programmingResponse: EpgProgrammingResponse): string | null {
  const firstRow = programmingResponse.rows?.[0];
  if (!firstRow) {
    getLog().error('No rows in EPG response');
    return null;
  }

  const firstVideoResource = firstRow.video_resources?.[0];
  if (!firstVideoResource) {
    getLog().error('No video resources in first row');
    return null;
  }

  const manifestUrl = firstVideoResource.manifest?.url;
  if (!manifestUrl) {
    getLog().error('No manifest URL in video resource');
    return null;
  }

  return manifestUrl;
}

/**
 * Quick helper to get manifest URL directly
 */
export async function getManifestUrlByContentId(
  contentId: string,
  deviceId?: string,
  platform?: string
): Promise<string | null> {
  const programming = await getEpgProgramming({
    contentId,
    deviceId,
    platform,
  });

  if (!programming) {
    return null;
  }

  return getManifestUrl(programming);
}

/**
 * Get full video resource details
 */
export function getVideoResourceDetails(programmingResponse: EpgProgrammingResponse): VideoResource | null {
  const firstRow = programmingResponse.rows?.[0];
  if (!firstRow) {
    return null;
  }

  return firstRow.video_resources?.[0] || null;
}

/**
 * Get all available video resources
 */
export function getAllVideoResources(programmingResponse: EpgProgrammingResponse): VideoResource[] {
  const firstRow = programmingResponse.rows?.[0];
  if (!firstRow) {
    return [];
  }

  return firstRow.video_resources || [];
}

