// SPDX-License-Identifier: MIT
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { AnnouncementBody, announcementTitle } from "./Announcement";

afterEach(cleanup);

describe("announcementTitle", () => {
  it("prefers the first markdown heading over the filename", () => {
    expect(announcementTitle("# 📣 FSAR 的第一封公告\n\nbody", "first-announcement.md")).toBe(
      "📣 FSAR 的第一封公告",
    );
  });

  it("uses the topmost heading, not a later one", () => {
    expect(announcementTitle("intro\n\n## Later\n\n# Not this one", "a.md")).toBe("Later");
  });

  it("strips emphasis markers from the heading", () => {
    expect(announcementTitle("## **Bold** and _italic_ and `code`", "a.md")).toBe(
      "Bold and italic and code",
    );
  });

  it("drops a trailing closing-hash sequence", () => {
    expect(announcementTitle("## Title ##", "a.md")).toBe("Title");
  });

  it("ignores a heading inside a fenced code block", () => {
    expect(announcementTitle("```\n# fake\n```\n\n# Real", "a.md")).toBe("Real");
  });

  it("falls back to the filename without its extension", () => {
    expect(announcementTitle("just prose, no heading", "first-announcement.md")).toBe(
      "first-announcement",
    );
  });

  it("treats an empty heading as absent", () => {
    expect(announcementTitle("#\n\ntext", "fallback.md")).toBe("fallback");
  });
});

describe("AnnouncementBody", () => {
  it("renders headings as real heading elements", () => {
    const screen = render(<AnnouncementBody body={"# Big\n\n## Small"} />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Big");
    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe("Small");
  });

  it("restores list markers, which preflight removes", () => {
    const screen = render(<AnnouncementBody body={"- one\n- two"} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByRole("list").className).toContain("list-disc");
  });

  it("renders a horizontal rule for a thematic break", () => {
    const screen = render(<AnnouncementBody body={"a\n\n---\n\nb"} />);
    expect(screen.getByRole("separator")).toBeTruthy();
  });

  it("renders a gfm table with cells", () => {
    const screen = render(
      <AnnouncementBody body={"| a | b |\n| - | - |\n| 1 | 2 |"} />,
    );
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getAllByRole("columnheader")).toHaveLength(2);
    expect(screen.getAllByRole("cell")).toHaveLength(2);
  });

  it("does not parse raw html", () => {
    const screen = render(
      <AnnouncementBody body={"# Hello\n\n<img src=x onerror=alert(1)>"} />,
    );
    expect(screen.queryByRole("img")).toBeNull();
  });
});
