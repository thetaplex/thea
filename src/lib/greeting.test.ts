import { describe, expect, it } from "vitest";
import { chatGreeting, timeOfDay } from "./greeting";

const at = (h: number) => new Date(2026, 10, 17, h, 30);

describe("chat greeting", () => {
  it("follows the local hour", () => {
    expect([at(5), at(11), at(12), at(17), at(18), at(23)].map(timeOfDay)).toEqual([
      "Good morning",
      "Good morning",
      "Good afternoon",
      "Good afternoon",
      "Good evening",
      "Good evening",
    ]);
  });

  it("asks what is on the user's mind", () => {
    expect(chatGreeting(at(9))).toBe("Good morning! What's on your mind?");
  });
});
