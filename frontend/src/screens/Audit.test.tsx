/** Панель аудита: находки по группам, чинятся только исправимые, выбор уходит адресами. */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { DeckDefect, DeckJob, DeckSlide } from "../api";
import { Audit } from "./Audit";
import { Deck } from "./Deck";

const defects: DeckDefect[] = [
  { id: "3:overflow:1", kind: "overflow", severity: "error", slide: 3,
    message: "текст не помещается", check: "overflow", nature: "deterministic",
    fixable: true, fix: "пересборка слайда с ужатым бюджетом", group: "геометрия" },
  { id: "5:overlap:2", kind: "overlap", severity: "warning", slide: 5,
    message: "объекты перекрываются", check: "overlap", nature: "deterministic",
    fixable: false, fix: "", group: "геометрия" },
  { id: "5:title_not_conclusion:3", kind: "audit", severity: "warning", slide: 5,
    message: "заголовок не вывод", check: "title_not_conclusion", nature: "contextual",
    fixable: false, fix: "", group: "смысл" },
];

function renderAudit(overrides: Partial<Parameters<typeof Audit>[0]> = {}) {
  const onRepair = vi.fn();
  const onSlide = vi.fn();
  render(
    <Audit
      defects={defects}
      checks={["overflow", "overlap", "title_not_conclusion"]}
      skipped={{ contrast: "нет шрифтов" }}
      busy={false}
      onSlide={onSlide}
      onRepair={onRepair}
      onClose={() => undefined}
      {...overrides}
    />,
  );
  return { onRepair, onSlide };
}

describe("панель аудита", () => {
  it("группирует находки и даёт флажок только исправимым", () => {
    renderAudit();
    expect(screen.getByText("геометрия")).toBeTruthy();
    expect(screen.getByText("смысл")).toBeTruthy();
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    expect(screen.getByText(/3 проверок · 3 находок/)).toBeTruthy();
    expect(screen.getByText(/contrast \(нет шрифтов\)/)).toBeTruthy();
    const button = screen.getByRole("button", { name: /Исправить выбранное/ });
    expect(button.textContent).toContain("0 из 1");
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("выбор отправляет адреса находок, клик по находке открывает слайд", () => {
    const { onRepair, onSlide } = renderAudit();
    fireEvent.click(screen.getByRole("checkbox"));
    const button = screen.getByRole("button", { name: /Исправить выбранное/ });
    expect(button.textContent).toContain("1 из 1");
    fireEvent.click(button);
    expect(onRepair).toHaveBeenCalledWith(["3:overflow:1"]);

    fireEvent.click(screen.getByRole("button", { name: /Слайд 5: заголовок не вывод/ }));
    expect(onSlide).toHaveBeenCalledWith(4);
  });

  it("во время ремонта кнопка занята", () => {
    renderAudit({ busy: true, repaired: [3] });
    expect(screen.getByText("Пересобираю…")).toBeTruthy();
    expect((screen.getByRole("checkbox") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText(/Пересобраны слайды 3/)).toBeTruthy();
  });
});

function slides(count: number): DeckSlide[] {
  return Array.from({ length: count }, (_, index) => ({
    n: index + 1, intent: "bullets", key_message: `s${index + 1}`, pattern: "p",
    pattern_name: "slide1.xml", archetype: "bullets", why: "", used_slots: 1,
    total_slots: 1, image: null,
  }));
}

describe("аудит на экране колоды", () => {
  it("кнопка со счётчиком открывает панель текущего варианта, ремонт уходит с его id", () => {
    const deck: DeckJob = {
      id: "d1", status: "ready", stage: "готово", variant: "balanced",
      slides: slides(3), defects,
      variants: [
        { id: "balanced", label: "Сбалансированно", tagline: "ровно", slides: slides(3),
          defects, checks: ["overflow"], download: null },
        { id: "compact", label: "Сжато", tagline: "плотнее", slides: slides(2),
          defects: [], checks: ["overflow"], download: null },
      ],
    };
    const onRepair = vi.fn();
    render(
      <Deck
        title="t" deck={deck} current={0} onCurrent={() => undefined} onBack={() => undefined}
        onDownload={() => undefined} onDownloadPdf={() => undefined} onShare={() => undefined}
        onRepair={onRepair}
      />,
    );
    const toggle = screen.getByRole("button", { name: /Аудит/ });
    expect(toggle.textContent).toContain("3");
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: /Исправить выбранное/ }));
    expect(onRepair).toHaveBeenCalledWith("balanced", ["3:overflow:1"]);

    fireEvent.click(screen.getByRole("tab", { name: /Сжато/ }));
    expect(screen.getByText("По чек-листу находок нет.")).toBeTruthy();
  });
});

describe("выбор находок переживает опрос колоды", () => {
  it("не сбрасывается, когда приходит тот же список новым массивом", () => {
    const onRepair = vi.fn();
    const props = {
      checks: ["overflow"], skipped: {}, busy: false,
      onSlide: () => undefined, onRepair, onClose: () => undefined,
    };
    const { rerender } = render(<Audit defects={defects} {...props} />);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: /Исправить выбранное/ }).textContent).toContain("1 из 1");

    // Опрос задачи: тот же состав находок, но другой массив и другие объекты.
    rerender(<Audit defects={defects.map((defect) => ({ ...defect }))} {...props} />);
    const button = screen.getByRole("button", { name: /Исправить выбранное/ });
    expect(button.textContent).toContain("1 из 1");
    expect((button as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(button);
    expect(onRepair).toHaveBeenCalledWith(["3:overflow:1"]);
  });

  it("сбрасывается, когда находки действительно стали другими", () => {
    const props = {
      checks: ["overflow"], skipped: {}, busy: false,
      onSlide: () => undefined, onRepair: vi.fn(), onClose: () => undefined,
    };
    const { rerender } = render(<Audit defects={defects} {...props} />);
    fireEvent.click(screen.getByRole("checkbox"));
    rerender(<Audit defects={[{ ...defects[0], id: "4:overflow:9" }]} {...props} />);
    expect(screen.getByRole("button", { name: /Исправить выбранное/ }).textContent).toContain("0 из 1");
  });
});
