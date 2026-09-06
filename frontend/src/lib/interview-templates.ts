import type { InterviewRoundConfig, InterviewRoundType } from "@/types";

export type InterviewAgent = { agent_id: string; name: string; role: string; description?: string; focal_competencies?: string[] };
export const interviewRoundLabels: Record<InterviewRoundType, string> = {
  introduction: "Introduction",
  technical: "Technical skills",
  behavioral: "Experience & decision making",
  hr_culture: "Collaboration & culture",
};

/** Keep the default competency's stored identifier separate from editable copy. */
export function formatTemplateFocusAreas(areas: string[]): string {
  return areas.map(area => area === "coding_problem_solving" ? "Coding & Problem Solving" : area).join(",");
}

export function parseTemplateFocusAreas(text: string): string[] {
  return text.split(",").map(area => area.trim() === "Coding & Problem Solving" ? "coding_problem_solving" : area);
}

/** Preserve arbitrary registered interviewers and avoid sharing editor arrays. */
export function copyTemplateRounds(rounds: InterviewRoundConfig[]): InterviewRoundConfig[] {
  return rounds.map((round, index) => {
    const agentIds = Array.from(new Set((round.agent_ids?.length ? round.agent_ids : round.agent_id ? [round.agent_id] : []).filter(Boolean)));
    return { type: round.type, duration_minutes: round.duration_minutes, focus_areas: round.focus_areas.map(area => area.trim()).filter(Boolean), enabled: round.enabled !== false, order_index: index + 1, agent_ids: agentIds, agent_id: agentIds[0] };
  });
}

export function templateDuration(rounds: InterviewRoundConfig[]): number {
  return rounds.filter(round => round.enabled !== false).reduce((total, round) => total + round.duration_minutes, 0);
}

export function validateTemplateRounds(rounds: InterviewRoundConfig[]): string | null {
  if (rounds.length > 24) return "Use no more than 24 interview rounds.";
  const active = rounds.filter(round => round.enabled !== false);
  if (!active.length) return "Add at least one active interview round.";
  if (templateDuration(rounds) > 60) return "Keep the total interview duration at 60 minutes or less.";
  for (let index = 0; index < rounds.length; index++) {
    const round = rounds[index];
    if (!Number.isInteger(round.duration_minutes) || round.duration_minutes < 1 || round.duration_minutes > 60) return `Round ${index + 1}: enter a duration between 1 and 60 minutes.`;
    if ((round.agent_ids?.length || 0) > 24) return `Round ${index + 1}: choose no more than 24 interviewers.`;
    if (round.focus_areas.length > 24) return `Round ${index + 1}: use no more than 24 focus areas.`;
    if (round.focus_areas.some(area => area.length > 160 || area.trim().startsWith("__intra_"))) return `Round ${index + 1}: use short, plain topic names for focus areas.`;
    if (round.enabled === false) continue;
    if (!(round.agent_ids?.length || round.agent_id)) return `Round ${index + 1}: choose at least one interviewer.`;
    if (!round.focus_areas.some(area => area.trim())) return `Round ${index + 1}: add at least one focus area.`;
  }
  return null;
}

export function newTemplateRound(order: number, agents: InterviewAgent[]): InterviewRoundConfig {
  return { type: "technical", duration_minutes: 15, focus_areas: ["coding_problem_solving"], enabled: true, order_index: order, agent_ids: agents[0] ? [agents[0].agent_id] : [], agent_id: agents[0]?.agent_id };
}
