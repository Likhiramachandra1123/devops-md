import { CommonModule } from "@angular/common";
import { Component, EventEmitter, Output, computed, inject, signal } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { Check, ChevronDown, Cpu, LucideAngularModule, RefreshCcw } from "lucide-angular";
import { ModelInfo } from "../../models/types";
import { ApiService } from "../../services/api.service";

@Component({
  selector: "app-model-picker",
  standalone: true,
  imports: [CommonModule, FormsModule, LucideAngularModule],
  host: { class: "relative inline-block" },
  template: `
    <button
      type="button"
      (click)="toggleOpen()"
      class="flex items-center gap-1.5 rounded-md border border-ink-200 bg-white px-2 py-1 text-xs text-ink-700 shadow-sm hover:border-brand-400 hover:bg-brand-50"
      [title]="selected() ? (selected()!.description ?? selected()!.display_name) : 'Choose model'"
    >
      <lucide-icon [img]="Cpu" class="h-3.5 w-3.5 text-brand-600"></lucide-icon>
      <span class="max-w-[140px] truncate font-medium">
        {{ selected()?.display_name ?? 'Loading…' }}
      </span>
      @if (selected() && selected()!.pricing_known) {
        <span class="text-ink-400">·</span>
        <span class="text-ink-500">
          \${{ fmtPrice(selected()!.input_price_per_mtok) }}/\${{ fmtPrice(selected()!.output_price_per_mtok) }}
        </span>
      }
      <lucide-icon [img]="ChevronDown" class="h-3.5 w-3.5 text-ink-400"></lucide-icon>
    </button>

    @if (open()) {
      <div class="fixed inset-0 z-40" (click)="close()"></div>
      <div class="absolute right-0 top-full z-50 mt-1 w-[380px] max-h-[520px] overflow-y-auto rounded-lg border border-ink-200 bg-white p-1 shadow-lg">
        <div class="flex items-center justify-between border-b border-ink-100 px-2 py-1.5">
          <div class="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
            Model
            @if (source()) {
              <span class="ml-1 rounded bg-ink-100 px-1 py-0.5 font-normal text-ink-500">
                {{ source() === 'api' ? 'live' : 'cached' }}
              </span>
            }
          </div>
          <button
            type="button"
            (click)="refresh(); $event.stopPropagation()"
            title="Refresh model list"
            class="rounded p-1 text-ink-400 hover:bg-ink-100 hover:text-ink-700"
          >
            <lucide-icon [img]="RefreshCcw" class="h-3.5 w-3.5"></lucide-icon>
          </button>
        </div>

        @if (loading()) {
          <div class="px-2 py-3 text-xs text-ink-500">Loading models…</div>
        } @else if (error()) {
          <div class="px-2 py-3 text-xs text-red-600">{{ error() }}</div>
        } @else if (models().length === 0) {
          <div class="px-2 py-3 text-xs text-ink-500">No models available.</div>
        } @else {
          @for (m of models(); track m.id) {
            <button
              type="button"
              (click)="pick(m)"
              class="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-brand-50"
              [class.bg-brand-50]="m.id === selectedId()"
            >
              <div class="mt-0.5 h-4 w-4 shrink-0">
                @if (m.id === selectedId()) {
                  <lucide-icon [img]="Check" class="h-4 w-4 text-brand-600"></lucide-icon>
                }
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1.5">
                  <span class="truncate text-xs font-medium text-ink-800">{{ m.display_name }}</span>
                  <span
                    class="rounded px-1 py-0.5 text-[10px] font-semibold uppercase"
                    [ngClass]="familyBadgeClass(m.family)"
                  >
                    {{ m.family }}
                  </span>
                  @if (m.is_default) {
                    <span class="rounded bg-ink-100 px-1 py-0.5 text-[10px] font-semibold uppercase text-ink-500">
                      default
                    </span>
                  }
                </div>
                <div class="mt-0.5 text-[11px] text-ink-500">
                  @if (m.pricing_known) {
                    <span class="font-medium text-ink-700">
                      \${{ fmtPrice(m.input_price_per_mtok) }} in
                    </span>
                    <span> · </span>
                    <span class="font-medium text-ink-700">
                      \${{ fmtPrice(m.output_price_per_mtok) }} out
                    </span>
                    <span class="text-ink-400"> per 1M tok</span>
                  } @else {
                    <span class="italic text-ink-400">pricing unknown</span>
                  }
                  @if (m.context_window > 0) {
                    <span> · {{ (m.context_window / 1000) | number:'1.0-0' }}K ctx</span>
                  }
                </div>
                @if (m.description) {
                  <div class="mt-0.5 text-[11px] text-ink-500">{{ m.description }}</div>
                }
                <div class="mt-0.5 truncate font-mono text-[10px] text-ink-400">{{ m.id }}</div>
              </div>
            </button>
          }
        }
      </div>
    }
  `,
})
export class ModelPickerComponent {
  private api = inject(ApiService);

  @Output() modelChange = new EventEmitter<string>();

  protected readonly Cpu = Cpu;
  protected readonly Check = Check;
  protected readonly ChevronDown = ChevronDown;
  protected readonly RefreshCcw = RefreshCcw;

  protected readonly models = signal<ModelInfo[]>([]);
  protected readonly loading = signal<boolean>(false);
  protected readonly error = signal<string | null>(null);
  protected readonly source = signal<"api" | "static" | null>(null);
  protected readonly selectedId = signal<string | null>(null);
  protected readonly open = signal<boolean>(false);

  protected readonly selected = computed(
    () => this.models().find((m) => m.id === this.selectedId()) ?? null,
  );

  constructor() {
    this.refresh();
  }

  refresh() {
    this.loading.set(true);
    this.error.set(null);
    this.api.listModels().subscribe({
      next: (res) => {
        this.models.set(res.models);
        this.source.set(res.source);
        // If nothing chosen yet, use backend's default. Preserve prior pick otherwise.
        if (!this.selectedId()) {
          const def =
            res.models.find((m) => m.id === res.default_model) ??
            res.models.find((m) => m.is_default) ??
            res.models[0];
          if (def) {
            this.selectedId.set(def.id);
            this.modelChange.emit(def.id);
          }
        }
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(err?.message ?? "Failed to load models");
        this.loading.set(false);
      },
    });
  }

  toggleOpen() {
    this.open.update((v) => !v);
  }

  close() {
    this.open.set(false);
  }

  pick(m: ModelInfo) {
    this.selectedId.set(m.id);
    this.modelChange.emit(m.id);
    this.close();
  }

  protected fmtPrice(v: number | null): string {
    if (v === null || v === undefined) return "—";
    if (v < 1) return v.toFixed(2);
    return v.toFixed(v % 1 === 0 ? 0 : 2);
  }

  protected familyBadgeClass(family: string): string {
    switch (family) {
      case "opus":
        return "bg-purple-100 text-purple-700";
      case "sonnet":
        return "bg-brand-100 text-brand-700";
      case "haiku":
        return "bg-emerald-100 text-emerald-700";
      default:
        return "bg-ink-100 text-ink-600";
    }
  }
}
