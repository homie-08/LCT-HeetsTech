/** Экран колоды: три варианта вёрстки переключаются на месте, ссылка на скачивание следует за выбором. */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { DeckJob, DeckSlide } from "../api";
import { Deck } from "./Deck";

function slides(count: number, prefix: string): DeckSlide[] {
  return Array.from({ length: count }, (_, index) => ({
    n: index + 1,
    intent: "bullets",
    key_message: `${prefix} ${index + 1}`,
    pattern: "p",
    pattern_name: "slide1.xml",
    archetype: "bullets",
    why: "",
    used_slots: 1,
    total_slots: 1,
    image: null,
  }));
}

const deck: DeckJob = {
  id: "d1",
  status: "ready",
  stage: "готово",
  variant: "balanced",
  slides: slides(13, "Сбалансированно"),
  download: "/api/decks/d1/file?variant=balanced",
  variants: [
    { id: "compact", label: "Сжато", tagline: "плотнее", slides: slides(11, "Сжато"),
      download: "/api/decks/d1/file?variant=compact" },
    { id: "balanced", label: "Сбалансированно", tagline: "ровно", slides: slides(13, "Сбалансированно"),
      download: "/api/decks/d1/file?variant=balanced" },
    { id: "spacious", label: "Просторно", tagline: "воздух", slides: slides(17, "Просторно"),
      download: "/api/decks/d1/file?variant=spacious" },
  ],
};

function renderDeck(onDownload = vi.fn(), onCurrent = vi.fn()) {
  render(
    <Deck
      title="Платформа «Поток»"
      deck={deck}
      current={0}
      onCurrent={onCurrent}
      onBack={() => undefined}
      onDownload={onDownload}
      onDownloadPdf={() => undefined}
      onShare={() => undefined}
    />,
  );
  return { onDownload, onCurrent };
}

describe("варианты вёрстки", () => {
  it("по умолчанию показан сбалансированный, все три доступны", () => {
    renderDeck();
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((tab) => tab.textContent)).toEqual([
      "Сжато11", "Сбалансированно13", "Просторно17",
    ]);
    expect(screen.getByRole("tab", { name: /Сбалансированно/ }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("1 / 13")).toBeTruthy();
  });

  it("переключение меняет слайды, счётчик и ссылку на скачивание", () => {
    const { onDownload, onCurrent } = renderDeck();
    fireEvent.click(screen.getByRole("tab", { name: /Просторно/ }));
    expect(screen.getByText("1 / 17")).toBeTruthy();
    expect(onCurrent).toHaveBeenCalledWith(0);

    fireEvent.click(screen.getByRole("button", { name: /Скачать \.pptx/ }));
    expect(onDownload).toHaveBeenCalledWith("/api/decks/d1/file?variant=spacious");
  });

  it("без вариантов переключатель не показывается", () => {
    render(
      <Deck
        title="t"
        deck={{ ...deck, variants: undefined }}
        current={0}
        onCurrent={() => undefined}
        onBack={() => undefined}
        onDownload={() => undefined}
        onDownloadPdf={() => undefined}
        onShare={() => undefined}
      />,
    );
    expect(screen.queryByRole("tablist")).toBeNull();
    expect(screen.getByText("1 / 13")).toBeTruthy();
  });
});

describe("экспорт следует за вариантом", () => {
  it("pdf и ссылка «Поделиться» берутся у выбранного варианта", () => {
    const onShare = vi.fn();
    const onDownloadPdf = vi.fn();
    const withExports: DeckJob = {
      ...deck,
      pdf: "/api/decks/d1/pdf?variant=balanced",
      html: "/api/decks/d1/html?variant=balanced",
      variants: deck.variants!.map((variant) => ({
        ...variant,
        pdf: variant.id === "compact" ? null : `/api/decks/d1/pdf?variant=${variant.id}`,
        html: variant.id === "compact" ? null : `/api/decks/d1/html?variant=${variant.id}`,
      })),
    };
    render(
      <Deck
        title="t" deck={withExports} current={0} onCurrent={() => undefined}
        onBack={() => undefined} onDownload={() => undefined}
        onDownloadPdf={onDownloadPdf} onShare={onShare}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Поделиться/ }));
    expect(onShare).toHaveBeenCalledWith("/api/decks/d1/html?variant=balanced");
    fireEvent.click(screen.getByRole("button", { name: /PDF/ }));
    expect(onDownloadPdf).toHaveBeenCalledWith("/api/decks/d1/pdf?variant=balanced");

    // У сжатого варианта файлы ещё готовятся: pdf нет, ссылка недоступна.
    fireEvent.click(screen.getByRole("tab", { name: /Сжато/ }));
    expect(screen.queryByRole("button", { name: /PDF/ })).toBeNull();
    expect((screen.getByRole("button", { name: /Поделиться/ }) as HTMLButtonElement).disabled).toBe(true);
  });
});
