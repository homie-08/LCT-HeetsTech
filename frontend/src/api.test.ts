import { afterEach, describe, expect, it, vi } from "vitest";
import { api, errorMessage, poll } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

function response(status: number, body: string): Response {
  return new Response(body, { status });
}

describe("сообщение об ошибке", () => {
  it("достаёт detail из ответа FastAPI", async () => {
    const text = await errorMessage(response(400, JSON.stringify({ detail: "нужен .pptx или .potx" })));
    expect(text).toBe("нужен .pptx или .potx");
  });

  it("склеивает подробности валидации", async () => {
    const body = JSON.stringify({ detail: [{ msg: "поле обязательно" }, { msg: "не число" }] });
    expect(await errorMessage(response(422, body))).toBe("поле обязательно; не число");
  });

  it("не падает на ответе, который не JSON", async () => {
    expect(await errorMessage(response(500, "Internal Server Error"))).toBe("Internal Server Error");
  });

  it("подставляет код, когда тело пустое", async () => {
    expect(await errorMessage(response(502, ""))).toBe("ошибка 502");
  });
});

describe("загрузка шаблона", () => {
  it("отдаёт причину отказа, а не сырой JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      response(400, JSON.stringify({ detail: "нужен .pptx или .potx" }))));
    await expect(api.uploadTemplate(new File([""], "readme.txt"))).rejects.toThrow(
      "нужен .pptx или .potx");
  });
});

describe("опрос состояния", () => {
  it("останавливается, когда задача готова", async () => {
    const load = vi.fn(async () => ({ status: "ready" as const }));
    const seen: unknown[] = [];
    poll(load, (value) => seen.push(value), 1);
    await vi.waitFor(() => expect(seen).toHaveLength(1));
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("переживает единичный сбой сети", async () => {
    let call = 0;
    const load = vi.fn(async () => {
      call += 1;
      if (call === 1) throw new Error("network");
      return { status: "ready" as const };
    });
    const seen: unknown[] = [];
    const failed = vi.fn();
    poll(load, (value) => seen.push(value), 1, failed);
    await vi.waitFor(() => expect(seen).toHaveLength(1));
    expect(failed).not.toHaveBeenCalled();
  });

  it("сдаётся и сообщает, когда сервис лежит", async () => {
    const load = vi.fn(async () => {
      throw new Error("Failed to fetch");
    });
    const failed = vi.fn();
    poll(load as never, () => undefined, 1, failed, 3);
    await vi.waitFor(() => expect(failed).toHaveBeenCalledWith("Failed to fetch"));
    expect(load).toHaveBeenCalledTimes(3);
  });

  it("больше не опрашивает после остановки", async () => {
    const load = vi.fn(async () => ({ status: "running" as const }));
    const stop = poll(load, () => undefined, 1);
    await vi.waitFor(() => expect(load).toHaveBeenCalled());
    stop();
    const after = load.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(load.mock.calls.length).toBeLessThanOrEqual(after + 1);
  });
});
