"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@volley/contracts";

import { apiClient } from "@/lib/api-client";

export type UploadStage = "reserving" | "uploading" | "validating";
type UploadTarget = components["schemas"]["UploadTargetOut"];
export type VideoDetectionStatus = components["schemas"]["VideoDetectionStatusOut"];
export type VideoDetectionFrame = components["schemas"]["VideoDetectionFrameOut"];

function uploadToSignedTarget(
  target: UploadTarget,
  file: File,
  onProgress: (progress: number) => void,
) {
  return new Promise<void>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open(target.method, target.url);
    Object.entries(target.headers).forEach(([name, value]) => request.setRequestHeader(name, value));
    request.upload.addEventListener("progress", (event) => {
      const total = event.lengthComputable ? event.total : file.size;
      if (total > 0) onProgress(Math.min(99, Math.round((event.loaded / total) * 100)));
    });
    request.addEventListener("load", () => {
      if (request.status >= 200 && request.status < 300) {
        onProgress(100);
        resolve();
      } else {
        reject(new Error(`Storage rejected the upload (${request.status})`));
      }
    });
    request.addEventListener("error", () => reject(new Error("Upload connection failed")));
    request.addEventListener("abort", () => reject(new Error("Upload cancelled")));
    request.send(file);
  });
}

export async function ingestVideo(
  file: File,
  matchId: string | null,
  callbacks: {
    onStage: (stage: UploadStage) => void;
    onProgress: (progress: number) => void;
  },
) {
  callbacks.onStage("reserving");
  callbacks.onProgress(0);
  const { data: reservation, error: reservationError } = await apiClient.POST("/api/v1/videos", {
    body: {
      filename: file.name,
      content_type: file.type || "application/octet-stream",
      size_bytes: file.size,
      ...(matchId ? { match_id: matchId } : {}),
    },
  });
  if (reservationError || !reservation) throw new Error("Could not reserve secure video storage");

  callbacks.onStage("uploading");
  await uploadToSignedTarget(reservation.upload, file, callbacks.onProgress);

  callbacks.onStage("validating");
  const { data: video, error: completionError } = await apiClient.POST(
    "/api/v1/videos/{video_id}/complete-upload",
    { params: { path: { video_id: reservation.video_id } } },
  );
  if (completionError || !video) throw new Error("Upload completed, but validation could not start");
  return video;
}

export function useVideos() {
  return useQuery({
    queryKey: ["videos"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/videos");
      if (error) throw new Error("Failed to load videos");
      return data;
    },
    refetchInterval: (query) =>
      query.state.data?.some((video) => video.status === "validating") ? 2500 : false,
  });
}

export function useDeleteVideo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (videoId: string) => {
      const { error } = await apiClient.DELETE("/api/v1/videos/{video_id}", {
        params: { path: { video_id: videoId } },
      });
      if (error) throw new Error("Failed to delete video");
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["videos"] });
    },
  });
}

export function useVideo(videoId: string) {
  return useQuery({
    queryKey: ["video", videoId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/videos/{video_id}", {
        params: { path: { video_id: videoId } },
      });
      if (error) throw new Error("Failed to load video");
      return data;
    },
  });
}

export function usePlaybackUrl(videoId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["video-playback-url", videoId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/videos/{video_id}/playback-url", {
        params: { path: { video_id: videoId } },
      });
      if (error) throw new Error("Failed to issue a playback URL");
      return data;
    },
    enabled,
    // The signed URL is short-lived (see DownloadTargetOut.expires_at) --
    // re-fetch a fresh one well before it can expire mid-playback rather
    // than surfacing a 403 partway through a scrub.
    staleTime: 4 * 60 * 1000,
    refetchInterval: 4 * 60 * 1000,
  });
}

export function useDetectionStatus(videoId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["video-detection-status", videoId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/videos/{video_id}/detection-status", {
        params: { path: { video_id: videoId } },
      });
      if (error) throw new Error("Failed to load detection status");
      return data;
    },
    enabled,
    refetchInterval: (query) =>
      query.state.data?.status === "queued" || query.state.data?.status === "running"
        ? 2000
        : false,
  });
}

export function useDetections(videoId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["video-detections", videoId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/videos/{video_id}/detections", {
        params: { path: { video_id: videoId } },
      });
      if (error) throw new Error("Failed to load detections");
      return data;
    },
    enabled,
  });
}

export function useTriggerDetection(videoId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (options?: {
      maxDurationSeconds?: number;
      startOffsetSeconds?: number;
      sampleFps?: number;
    }) => {
      const { maxDurationSeconds, startOffsetSeconds, sampleFps } = options ?? {};
      const body =
        maxDurationSeconds != null || startOffsetSeconds != null || sampleFps != null
          ? {
              max_duration_seconds: maxDurationSeconds,
              start_offset_seconds: startOffsetSeconds,
              sample_fps: sampleFps,
            }
          : null;
      const { data, error } = await apiClient.POST("/api/v1/videos/{video_id}/detect", {
        params: { path: { video_id: videoId } },
        body,
      });
      if (error) throw new Error("Failed to start detection");
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["video-detection-status", videoId] });
    },
  });
}
