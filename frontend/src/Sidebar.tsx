/** Боковая панель: логотип, новая презентация, недавние, пользователь. */

import { PanelLeft, Plus, Settings, Trash, VkLogo } from "./ui";

export interface RecentDeck {
  /** Идентификатор собранной колоды; пустой у записей старого формата. */
  id: string;
  title: string;
}

export interface SidebarProps {
  open: boolean;
  recent: RecentDeck[];
  llmOn: boolean;
  onToggle: () => void;
  onNew: () => void;
  onToggleLlm: () => void;
  onOpenRecent: (item: RecentDeck) => void;
  onDeleteRecent: (item: RecentDeck) => void;
}

export function Sidebar({ open, recent, llmOn, onToggle, onNew, onToggleLlm,
                          onOpenRecent, onDeleteRecent }: SidebarProps) {
  return (
    <aside
      className="flex w-[264px] shrink-0 flex-col border-r border-edge-panel bg-panel
                 px-3 py-3.5 transition-[margin] duration-[380ms] ease-panel"
      style={{ marginLeft: open ? 0 : -264 }}
      aria-hidden={!open}
    >
      <div className="flex items-center gap-2.5 px-1">
        <VkLogo size={28} />
        {/* Unbounded заметно шире Geologica — логотипу хватает 14px и веса 400. */}
        <span className="display text-[14px] font-normal text-ink-primary">VK Slides</span>
        <button
          type="button"
          onClick={onToggle}
          aria-label="Скрыть панель"
          className="icon-button ml-auto h-8 w-8 rounded-[10px] border-transparent"
        >
          <PanelLeft size={17} />
        </button>
      </div>

      <button
        type="button"
        onClick={onNew}
        className="mt-4 flex h-[38px] items-center gap-2 rounded-xl border border-edge-control
                   bg-white/[0.04] px-3 text-[13.5px] font-medium text-ink-secondary
                   transition-colors duration-150 hover:border-edge-hover hover:text-vk-light"
      >
        <Plus size={15} />
        Новая презентация
        <span className="ml-auto text-[11px] text-ink-label">Ctrl K</span>
      </button>

      {/* Раздел появляется, когда есть что показать: пустой заголовок
          «Недавние» выглядит как незагрузившийся список. */}
      {recent.length > 0 && (
        <div className="mt-6 px-1">
          <span className="label">Недавние</span>
        </div>
      )}
      <nav className="mt-2 flex flex-col gap-0.5">
        {recent.map((item) => (
          <div
            key={item.id || item.title}
            className="group flex items-center rounded-[10px] transition-colors
                       duration-150 hover:bg-white/[0.06]"
          >
            <button
              type="button"
              onClick={() => onOpenRecent(item)}
              title={item.title}
              className="min-w-0 flex-1 truncate px-2.5 py-2 text-left text-[13.5px]
                         text-ink-muted transition-colors duration-150
                         group-hover:text-ink-primary"
            >
              {item.title}
            </button>
            {/* Корзина видна при наведении и с клавиатуры — постоянный ряд
                мусорок превращает список проектов в кладбище. */}
            <button
              type="button"
              aria-label={`Удалить «${item.title}»`}
              onClick={() => onDeleteRecent(item)}
              className="mr-1.5 flex h-7 w-7 shrink-0 items-center justify-center
                         rounded-[8px] text-ink-label opacity-0 transition-all
                         duration-150 hover:text-[#FF6B6B] focus-visible:opacity-100
                         group-hover:opacity-100"
            >
              <Trash size={14} />
            </button>
          </div>
        ))}
      </nav>

      <div className="mt-auto flex items-center gap-2.5 border-t border-edge-panel px-1 pt-3">
        <span
          className="flex h-8 w-8 items-center justify-center rounded-pill bg-vk-deep
                     text-[12px] font-semibold text-vk-light"
        >
          АК
        </span>
        <span className="text-[13.5px] text-ink-secondary">Анна Ковалёва</span>
        {/* Единственная настройка, которая сейчас на что-то влияет: с моделью
            сервис переписывает и планирует, без неё работает на эвристиках. */}
        <button
          type="button"
          aria-label={llmOn ? "Выключить модель" : "Включить модель"}
          title={llmOn ? "Модель включена" : "Модель выключена"}
          aria-pressed={llmOn}
          onClick={onToggleLlm}
          className={`icon-button ml-auto h-8 w-8 rounded-[10px] border-transparent ${
            llmOn ? "text-vk-light" : ""
          }`}
        >
          <Settings size={16} />
        </button>
      </div>
    </aside>
  );
}
