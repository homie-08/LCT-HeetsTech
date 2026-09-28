import type { TemplateJob } from "../api";

/** Дизайн-система шаблона: то, что сервис извлёк из файла, с указанием источника. */
export function DesignSystemView({ template }: { template: TemplateJob }) {
  const { palette, typography, geometry, source } = template;
  if (!palette || !typography || !geometry) return null;

  return (
    <div className="card p-5">
      <div className="mb-4 flex items-baseline justify-between gap-3">
        <h2 className="text-lg font-semibold">{source?.file}</h2>
        <span className="text-sm text-neutral-500">
          {source?.slide_size.ratio} · {source?.layouts} макетов ·{" "}
          {source?.example_slides} слайдов-примеров
        </span>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <section>
          <div className="label mb-2">Палитра темы</div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(palette.theme).map(([name, color]) => (
              <div
                key={name}
                title={`${name}: ${color}`}
                className="h-8 w-8 rounded-md border border-neutral-200"
                style={{ background: color }}
              />
            ))}
          </div>

          <div className="label mb-2 mt-4">Роли и происхождение</div>
          <dl className="space-y-1 text-sm">
            {Object.entries(palette.roles).map(([role, color]) => (
              <div key={role} className="flex items-center gap-2">
                <span
                  className="h-4 w-4 shrink-0 rounded border border-neutral-200"
                  style={{ background: color }}
                />
                <code className="font-mono text-xs">{role}</code>
                <span className="font-mono text-xs text-neutral-500">{color}</span>
                <span className="truncate text-xs text-neutral-400">
                  ← {palette.role_provenance[role]}
                </span>
              </div>
            ))}
          </dl>
        </section>

        <section>
          <div className="label mb-2">Типографика</div>
          <p className="text-sm">
            {typography.fonts.major}
            {typography.fonts.minor !== typography.fonts.major && ` / ${typography.fonts.minor}`}
            {typography.fonts.embedded.length > 0 && (
              <span className="chip ml-2">вшит в файл</span>
            )}
          </p>
          <p className="mt-1 font-mono text-xs text-neutral-500">
            шкала: {typography.scale_pt.join(", ")}
          </p>
          <dl className="mt-3 space-y-1 text-sm">
            {Object.entries(typography.styles).slice(0, 7).map(([name, style]) => (
              <div key={name} className="flex items-baseline gap-2">
                <code className="font-mono text-xs text-neutral-500">{name}</code>
                <span style={{ color: style.color }}>{style.font}</span>
                <span className="text-xs text-neutral-400">{style.size_pt} pt</span>
              </div>
            ))}
          </dl>
        </section>

        <section>
          <div className="label mb-2">Сетка</div>
          <dl className="space-y-1 text-sm">
            <Row name="поля" value={`л ${geometry.margins.l} · п ${geometry.margins.r} · в ${geometry.margins.t} · н ${geometry.margins.b}`} />
            <Row name="колонок" value={String(geometry.columns.count)} />
            <Row name="межколонник" value={String(geometry.columns.gutter)} />
            <Row name="безопасная зона" value={geometry.safe_area.join(", ")} />
          </dl>
          {template.warnings && template.warnings.length > 0 && (
            <ul className="mt-3 space-y-1 text-xs text-amber-700">
              {template.warnings.map((warning) => (
                <li key={warning}>⚠ {warning}</li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

function Row({ name, value }: { name: string; value: string }) {
  return (
    <div className="flex gap-2">
      <dt className="w-32 shrink-0 text-neutral-500">{name}</dt>
      <dd className="font-mono text-xs">{value}</dd>
    </div>
  );
}
