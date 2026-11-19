/** "Good morning", "Good afternoon" or "Good evening" for the local hour of `now`. */
export function timeOfDay(now: Date = new Date()): string {
  const h = now.getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

/** The greeting of a chat without a project, which has no persona. */
export function chatGreeting(now: Date = new Date()): string {
  return `${timeOfDay(now)}! What's on your mind?`;
}
