export type Row = Record<string, any>;
export type Platform = "youtube" | "tiktok" | "instagram";
export type StyleId = "cinematic-gaming" | "high-energy-action" | "kinetic-typography" | "reaction-split-screen" | "interactive-tutorial" | "comparison-vs" | "retro-arcade" | "minimal-premium";
export type StoryRole = "hook" | "context" | "development" | "payoff";
export type FrameSample = { timestamp: number; thumbnail: string; change: number; motion: number; focus_x: number; focus_y: number; brightness: number; sharpness: number; focus_confidence: "low" };
export type SourceAnalysis = {
  source_id: string; fingerprint: string; duration: number; width: number; height: number;
  frames: FrameSample[]; scene_changes: number[]; cues: { start: number; end: number; text: string }[];
  limitations: string[]; warnings: string[]; method: "local_measured"; analyzed_at: string;
  audio: { status: "unavailable" | "measured"; reason?: string; samples: { timestamp: number; rms: number }[] };
};
export type SourceDescriptor = { id: string; filename: string; media_info: { duration: number; width: number; height: number; [key: string]: any }; rights_confirmed?: boolean; original_creator?: boolean; [key: string]: any };
export type StyleDefinition = {
  id: StyleId; name: string; description: string; typography: string; motion_graphics: string;
  transition_behavior: string; composition: "fill" | "fit_blur" | "split"; pacing: string;
  caption_treatment: string; background: string; sound: string; palette: string[];
  transition: "cut" | "fade"; effect: "none" | "contrast" | "retro";
  caption_animation: "none" | "fade" | "pop" | "slide"; requires_secondary: boolean;
};
export type Shot = {
  id: string; source_id: string; role: StoryRole; start: number; end: number;
  crop_x: number; crop_y: number; crop_x_end?: number; crop_y_end?: number; zoom: number;
  composition: "fill" | "fit_blur" | "split"; transition: "cut" | "fade"; effect: "none" | "contrast" | "retro";
  overlay_text: string; overlay_position: "top" | "bottom"; rationale: string;
  source_evidence: string[]; thumbnail: string; manual_modified?: boolean; locked?: boolean;
  secondary_source_id?: string; secondary_start?: number;
};
export type HookAssessment = { score: number; is_heuristic: true; accuracy: "unverified" | "source_quote" | "user_supplied"; factors: { name: string; score: number; explanation: string }[]; warning: string };
export type CreativeConcept = {
  id: string; title: string; kind: "high-engagement" | "cinematic" | "creative-storytelling";
  audience: string; duration: number; hook: string; hook_alternatives: string[]; hook_assessment: HookAssessment;
  shots: Shot[]; style_id: StyleId; caption_settings: CaptionSettings; audio_treatment: "source" | "mute";
  ending_strategy: string; distinct_reason: string; compliance_notes: string[]; recommendation_reason: string;
  mode: "assisted_manual"; manual_decisions: string; generation_method: "local_assisted";
  provider_status: "not_configured"; diversity: { similarity: number; repeated_patterns: string[]; warning: string | null };
  output_width: 1080 | 720 | 540; output_height: 1920 | 1280 | 960;
  selected_title: string; description: string; hashtags: string[]; user_modified?: boolean; created_at: string;
};
export type CaptionSettings = { enabled: boolean; font_size: number; color: string; highlight: string; safe_top: number; safe_bottom: number; animation: "none" | "fade" | "pop" | "slide"; position: "lower" | "upper" | "center" };
export type CreativeOptions = {
  duration?: number; pace?: "auto" | "relaxed" | "balanced" | "energetic"; style?: StyleId | "auto";
  audience?: string; title?: string; description?: string; hashtags?: string[]; platform?: Platform;
  captions?: Partial<CaptionSettings>; audio?: "source" | "mute"; mode?: "assisted" | "manual";
  manual_decisions?: string; output_height?: 1920 | 1280 | 960; variation?: number;
};
export type CreativeCheck = { rule: string; status: "PASS" | "FAIL" | "REVIEW_REQUIRED"; detail: string; blocking: boolean; classification: "mandatory" | "prohibited" | "recommended" | "unclear" };
export type PreflightResult = { status: "PASS" | "FAIL" | "REVIEW_REQUIRED"; render_allowed: boolean; publish_ready: false; assisted_manual_required: boolean; checks: CreativeCheck[]; missing_footage: string[] };
export type ConceptBatch = { concepts: CreativeConcept[]; recommended_id: string | null; recommendation: string; limitations: string[]; analysis_method: "local_measured"; generation_method: "local_assisted"; provider_status: "not_configured"; unavailable_reasons: string[] };
export type GenerateInput = { source: SourceDescriptor; analysis: SourceAnalysis; rules: Row; options?: CreativeOptions; history?: CreativeConcept[]; originalSources?: SourceDescriptor[] };
