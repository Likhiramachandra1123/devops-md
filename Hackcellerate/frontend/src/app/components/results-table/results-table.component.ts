import { CommonModule } from "@angular/common";
import { Component, EventEmitter, Output, computed, effect, input, signal } from "@angular/core";
import { FormsModule } from "@angular/forms";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  ExternalLink,
  Filter,
  LucideAngularModule,
  Search,
  X,
} from "lucide-angular";
import { SearchResult } from "../../models/types";

const PAGE_SIZES = [10, 25, 50];
const SCORE_OPTIONS: { label: string; value: number }[] = [
  { label: "Any score", value: 0 },
  { label: "≥ 0.30", value: 0.3 },
  { label: "≥ 0.50", value: 0.5 },
  { label: "≥ 0.70", value: 0.7 },
  { label: "≥ 0.90", value: 0.9 },
];
const ALL = "__all__";

@Component({
  selector: "app-results-table",
  standalone: true,
  imports: [CommonModule, FormsModule, LucideAngularModule],
  host: { class: "block h-full min-h-0" },
  template: `
    <div class="flex h-full min-h-0 flex-col">
      <!-- Header -->
      <div class="flex shrink-0 items-center justify-between border-b border-ink-200 bg-white px-4 py-3">
        <div>
          <h2 class="text-sm font-semibold text-ink-800">Search Results</h2>
          @if (query()) {
            <p class="text-xs text-ink-500 truncate max-w-[420px]">
              for <span class="font-medium text-ink-700">"{{ query() }}"</span>
              <span class="ml-1 text-ink-400">
                ·
                @if (isFiltered()) {
                  {{ filtered().length }} of {{ results().length }}
                } @else {
                  {{ results().length }}
                }
                result{{ results().length === 1 ? '' : 's' }}
              </span>
            </p>
          }
        </div>
        <button
          type="button"
          (click)="close.emit()"
          title="Close results panel"
          class="flex h-8 w-8 items-center justify-center rounded-md text-ink-500 hover:bg-ink-100 hover:text-ink-700"
        >
          <lucide-icon [img]="X" class="h-4 w-4"></lucide-icon>
        </button>
      </div>

      <!-- Filter bar -->
      <div class="flex shrink-0 flex-wrap items-center gap-2 border-b border-ink-100 bg-ink-50/40 px-4 py-2">
        <div class="relative min-w-[200px] flex-1">
          <span class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-2 text-ink-400">
            <lucide-icon [img]="Search" class="h-3.5 w-3.5"></lucide-icon>
          </span>
          <input
            type="text"
            [ngModel]="textFilter()"
            (ngModelChange)="textFilter.set($event)"
            placeholder="Filter titles & snippets…"
            class="h-8 w-full rounded-md border border-ink-200 bg-white pl-8 pr-2 text-xs text-ink-700 placeholder:text-ink-400 focus:border-brand-400 focus:outline-none focus:ring-1 focus:ring-brand-100"
          />
        </div>

        <select
          [ngModel]="sourceFilter()"
          (ngModelChange)="sourceFilter.set($event)"
          class="h-8 rounded-md border border-ink-200 bg-white px-2 text-xs text-ink-700 focus:border-brand-400 focus:outline-none"
          title="Source"
        >
          <option [value]="ALL">All sources</option>
          @for (s of availableSources(); track s) {
            <option [value]="s">{{ s }}</option>
          }
        </select>

        <select
          [ngModel]="docTypeFilter()"
          (ngModelChange)="docTypeFilter.set($event)"
          class="h-8 rounded-md border border-ink-200 bg-white px-2 text-xs text-ink-700 focus:border-brand-400 focus:outline-none"
          title="Document type"
        >
          <option [value]="ALL">All types</option>
          @for (t of availableTypes(); track t) {
            <option [value]="t">{{ t }}</option>
          }
        </select>

        <select
          [ngModel]="minScore()"
          (ngModelChange)="minScore.set(+$event)"
          class="h-8 rounded-md border border-ink-200 bg-white px-2 text-xs text-ink-700 focus:border-brand-400 focus:outline-none"
          title="Minimum score"
        >
          @for (o of scoreOptions; track o.value) {
            <option [value]="o.value">{{ o.label }}</option>
          }
        </select>

        @if (isFiltered()) {
          <button
            type="button"
            (click)="clearFilters()"
            class="inline-flex h-8 items-center gap-1 rounded-md border border-ink-200 bg-white px-2 text-xs font-medium text-ink-600 hover:border-brand-300 hover:text-brand-700"
            title="Clear filters"
          >
            <lucide-icon [img]="Filter" class="h-3 w-3"></lucide-icon>
            Clear
          </button>
        }
      </div>

      @if (summary()) {
        <div class="shrink-0 border-b border-ink-100 bg-brand-50/40 px-4 py-2 text-xs text-ink-700">
          <span class="font-semibold text-brand-700">Summary:</span> {{ summary() }}
        </div>
      }

      <!-- Table -->
      <div class="min-h-0 flex-1 overflow-auto bg-white">
        <table class="min-w-full text-sm">
          <thead class="sticky top-0 bg-ink-50 text-[11px] font-semibold uppercase tracking-wide text-ink-500">
            <tr>
              <th class="w-8 px-3 py-2"></th>
              <th class="px-3 py-2 text-left">Title</th>
              <th class="px-3 py-2 text-left">Source</th>
              <th class="px-3 py-2 text-left">Score</th>
              <th class="px-3 py-2 text-left">Data Provider</th>
              <th class="px-3 py-2 text-left">Publication</th>
              <th class="px-3 py-2 text-left">Link</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-ink-100">
            @for (r of paged(); track r.chunk_id || r.index) {
              <tr class="align-top hover:bg-ink-50/60">
                <td class="px-3 py-2.5">
                  <button
                    type="button"
                    (click)="toggle(r.index)"
                    class="flex h-6 w-6 items-center justify-center rounded text-ink-400 hover:bg-ink-100 hover:text-ink-700"
                  >
                    @if (expanded().has(r.index)) {
                      <lucide-icon [img]="ChevronDown" class="h-4 w-4"></lucide-icon>
                    } @else {
                      <lucide-icon [img]="ChevronRight" class="h-4 w-4"></lucide-icon>
                    }
                  </button>
                </td>
                <td class="px-3 py-2.5">
                  <div class="font-medium text-ink-800">{{ r.title }}</div>
                  <div class="text-[11px] text-ink-400 font-mono truncate max-w-[320px]">{{ r.chunk_id }}</div>
                </td>
                <td class="px-3 py-2.5 text-ink-700">{{ r.source }}</td>
                <td class="px-3 py-2.5">
                  <div class="flex items-center gap-1.5">
                    <div class="h-1.5 w-16 overflow-hidden rounded bg-ink-100">
                      <div class="h-full bg-brand-500" [style.width.%]="r.score * 100"></div>
                    </div>
                    <span class="font-mono text-[11px] text-ink-600">{{ r.score.toFixed(2) }}</span>
                  </div>
                </td>
                <td class="px-3 py-2.5 text-ink-700">{{ providerOf(r) }}</td>
                <td class="px-3 py-2.5 text-ink-700">{{ dateOf(r) }}</td>
                <td class="px-3 py-2.5">
                  @if (r.url) {
                    <a
                      [href]="r.url"
                      target="_blank"
                      rel="noopener"
                      class="inline-flex items-center gap-1 text-brand-600 hover:text-brand-700"
                    >
                      Open <lucide-icon [img]="ExternalLink" class="h-3 w-3"></lucide-icon>
                    </a>
                  } @else {
                    <span class="text-ink-300">—</span>
                  }
                </td>
              </tr>
              @if (expanded().has(r.index)) {
                <tr class="bg-ink-50/40">
                  <td></td>
                  <td colspan="6" class="px-3 pb-4 pt-1 text-xs text-ink-700">
                    <div class="space-y-3 rounded-md border border-ink-100 bg-white p-4 shadow-sm">
                      <!-- Header row: title + open link -->
                      <div class="flex items-start justify-between gap-3">
                        <div class="min-w-0">
                          <div class="text-sm font-semibold text-ink-800 break-words">{{ r.title }}</div>
                          <div class="mt-0.5 text-[11px] text-ink-500">
                            <span class="font-medium text-ink-700">{{ r.source }}</span>
                            @if (typeOf(r); as t) {
                              <span class="text-ink-400"> · </span>
                              <span>{{ t }}</span>
                            }
                            <span class="text-ink-400"> · </span>
                            <span class="font-mono">score {{ r.score.toFixed(2) }}</span>
                          </div>
                        </div>
                        @if (r.url) {
                          <a
                            [href]="r.url"
                            target="_blank"
                            rel="noopener"
                            class="inline-flex shrink-0 items-center gap-1 text-brand-600 hover:text-brand-700"
                          >
                            Open source <lucide-icon [img]="ExternalLink" class="h-3 w-3"></lucide-icon>
                          </a>
                        }
                      </div>

                      <!-- Metadata grid (only shows keys that are present + meaningful) -->
                      @if (metaEntries(r).length > 0) {
                        <div class="grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2 lg:grid-cols-3">
                          @for (kv of metaEntries(r); track kv.key) {
                            <div class="flex flex-col">
                              <span class="text-[10px] font-semibold uppercase tracking-wide text-ink-400">{{ kv.label }}</span>
                              <span class="text-[12px] text-ink-700 break-words">{{ kv.value }}</span>
                            </div>
                          }
                        </div>
                      }

                      <!-- Full text -->
                      <div>
                        <div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-500">Excerpt</div>
                        <p class="whitespace-pre-wrap break-words leading-relaxed text-[13px] text-ink-700">{{ r.text || r.snippet }}</p>
                      </div>

                      <!-- IDs footer -->
                      <div class="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-ink-100 pt-2 text-[10px] font-mono text-ink-400">
                        @if (r.doc_id) {
                          <span>doc_id: {{ r.doc_id }}</span>
                        }
                        @if (r.chunk_id) {
                          <span>chunk_id: {{ r.chunk_id }}</span>
                        }
                      </div>
                    </div>
                  </td>
                </tr>
              }
            } @empty {
              <tr>
                <td colspan="7" class="px-3 py-10 text-center text-sm text-ink-400">
                  @if (results().length > 0) {
                    No results match your filters.
                  } @else {
                    No results.
                  }
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      @if (filtered().length > 0) {
        <div class="flex shrink-0 items-center justify-between border-t border-ink-200 bg-white px-4 py-2">
          <div class="text-xs text-ink-500">
            Showing
            <span class="font-medium text-ink-700">{{ startIndex() + 1 }}</span>
            –<span class="font-medium text-ink-700">{{ endIndex() }}</span>
            of <span class="font-medium text-ink-700">{{ filtered().length }}</span>
            @if (isFiltered()) {
              <span class="text-ink-400"> (filtered from {{ results().length }})</span>
            }
          </div>

          <div class="flex items-center gap-3">
            <label class="flex items-center gap-1 text-xs text-ink-500">
              Rows per page
              <select
                [value]="pageSize()"
                (change)="onPageSizeChange($event)"
                class="rounded border border-ink-200 bg-white px-1.5 py-0.5 text-xs text-ink-700 focus:border-brand-400 focus:outline-none"
              >
                @for (n of pageSizes; track n) {
                  <option [value]="n">{{ n }}</option>
                }
              </select>
            </label>

            <div class="flex items-center gap-0.5">
              <button
                type="button"
                (click)="goTo(1)"
                [disabled]="page() === 1"
                title="First page"
                class="flex h-7 w-7 items-center justify-center rounded text-ink-500 hover:bg-ink-100 hover:text-ink-700 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent"
              >
                <lucide-icon [img]="ChevronsLeft" class="h-4 w-4"></lucide-icon>
              </button>
              <button
                type="button"
                (click)="goTo(page() - 1)"
                [disabled]="page() === 1"
                title="Previous"
                class="flex h-7 w-7 items-center justify-center rounded text-ink-500 hover:bg-ink-100 hover:text-ink-700 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent"
              >
                <lucide-icon [img]="ChevronLeft" class="h-4 w-4"></lucide-icon>
              </button>

              <span class="px-2 text-xs font-medium text-ink-700">
                Page {{ page() }} / {{ totalPages() }}
              </span>

              <button
                type="button"
                (click)="goTo(page() + 1)"
                [disabled]="page() >= totalPages()"
                title="Next"
                class="flex h-7 w-7 items-center justify-center rounded text-ink-500 hover:bg-ink-100 hover:text-ink-700 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent"
              >
                <lucide-icon [img]="ChevronRight" class="h-4 w-4"></lucide-icon>
              </button>
              <button
                type="button"
                (click)="goTo(totalPages())"
                [disabled]="page() >= totalPages()"
                title="Last page"
                class="flex h-7 w-7 items-center justify-center rounded text-ink-500 hover:bg-ink-100 hover:text-ink-700 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent"
              >
                <lucide-icon [img]="ChevronsRight" class="h-4 w-4"></lucide-icon>
              </button>
            </div>
          </div>
        </div>
      }
    </div>
  `,
})
export class ResultsTableComponent {
  results = input.required<SearchResult[]>();
  query = input<string>("");
  summary = input<string | null | undefined>(undefined);
  @Output() close = new EventEmitter<void>();

  protected readonly expanded = signal<Set<number>>(new Set());
  protected readonly page = signal<number>(1);
  protected readonly pageSize = signal<number>(10);
  protected readonly pageSizes = PAGE_SIZES;

  // Filter state
  protected readonly textFilter = signal<string>("");
  protected readonly sourceFilter = signal<string>(ALL);
  protected readonly docTypeFilter = signal<string>(ALL);
  protected readonly minScore = signal<number>(0);
  protected readonly scoreOptions = SCORE_OPTIONS;
  protected readonly ALL = ALL;

  // Derived
  protected readonly availableSources = computed(() => {
    const set = new Set<string>();
    for (const r of this.results()) {
      const v = (r.source || "").trim();
      if (v) set.add(v);
    }
    return Array.from(set).sort();
  });

  protected readonly availableTypes = computed(() => {
    const set = new Set<string>();
    for (const r of this.results()) {
      const t = (r.metadata?.["doc_type"] as string | undefined) || "";
      if (t) set.add(t);
    }
    return Array.from(set).sort();
  });

  protected readonly isFiltered = computed(
    () =>
      this.textFilter().trim().length > 0 ||
      this.sourceFilter() !== ALL ||
      this.docTypeFilter() !== ALL ||
      this.minScore() > 0,
  );

  protected readonly filtered = computed(() => {
    const q = this.textFilter().trim().toLowerCase();
    const src = this.sourceFilter();
    const typ = this.docTypeFilter();
    const min = this.minScore();
    return this.results().filter((r) => {
      if (src !== ALL && r.source !== src) return false;
      if (typ !== ALL && (r.metadata?.["doc_type"] ?? "") !== typ) return false;
      if (r.score < min) return false;
      if (q) {
        const hay = `${r.title} ${r.snippet}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  });

  protected readonly totalPages = computed(() =>
    Math.max(1, Math.ceil(this.filtered().length / this.pageSize())),
  );
  protected readonly startIndex = computed(
    () => (this.page() - 1) * this.pageSize(),
  );
  protected readonly endIndex = computed(() =>
    Math.min(this.filtered().length, this.startIndex() + this.pageSize()),
  );
  protected readonly paged = computed(() =>
    this.filtered().slice(this.startIndex(), this.endIndex()),
  );

  protected readonly ChevronDown = ChevronDown;
  protected readonly ChevronRight = ChevronRight;
  protected readonly ChevronLeft = ChevronLeft;
  protected readonly ChevronsLeft = ChevronsLeft;
  protected readonly ChevronsRight = ChevronsRight;
  protected readonly ExternalLink = ExternalLink;
  protected readonly Filter = Filter;
  protected readonly Search = Search;
  protected readonly X = X;

  constructor() {
    // Reset page & expansion when the underlying results change (new search).
    effect(() => {
      this.results();
      this.page.set(1);
      this.expanded.set(new Set());
      this.textFilter.set("");
      this.sourceFilter.set(ALL);
      this.docTypeFilter.set(ALL);
      this.minScore.set(0);
    });

    // Reset to page 1 whenever the filtered set changes (filter change).
    effect(() => {
      this.filtered();
      const pages = this.totalPages();
      if (this.page() > pages) this.page.set(pages);
    });
  }

  protected toggle(idx: number) {
    const next = new Set(this.expanded());
    if (next.has(idx)) next.delete(idx);
    else next.add(idx);
    this.expanded.set(next);
  }

  protected goTo(p: number) {
    const clamped = Math.max(1, Math.min(this.totalPages(), p));
    this.page.set(clamped);
  }

  protected onPageSizeChange(e: Event) {
    const val = Number((e.target as HTMLSelectElement).value);
    if (!Number.isFinite(val) || val <= 0) return;
    this.pageSize.set(val);
    this.page.set(1);
  }

  protected clearFilters() {
    this.textFilter.set("");
    this.sourceFilter.set(ALL);
    this.docTypeFilter.set(ALL);
    this.minScore.set(0);
    this.page.set(1);
  }

  protected providerOf(r: SearchResult): string {
    const meta = r.metadata ?? {};
    return String(meta["provider"] ?? meta["data_provider"] ?? r.source ?? "—");
  }

  protected dateOf(r: SearchResult): string {
    const meta = r.metadata ?? {};
    return String(meta["publication_date"] ?? meta["date"] ?? meta["year"] ?? "—");
  }

  protected typeOf(r: SearchResult): string {
    const meta = r.metadata ?? {};
    const t = (meta["doc_type"] ?? "") as string;
    if (!t) return "";
    return t.replace(/_/g, " ");
  }

  /**
   * Curated set of metadata keys to surface in the expanded row, in display order.
   * Keys not present in `r.metadata` are silently skipped. Values that look like
   * arrays get joined; empty / trivial values ("unknown", "N/A", "") are dropped.
   */
  private static readonly META_FIELDS: { key: string; label: string }[] = [
    { key: "manufacturer", label: "Manufacturer" },
    { key: "applicant", label: "Applicant" },
    { key: "sponsor", label: "Sponsor" },
    { key: "device_classification", label: "Device Classification" },
    { key: "review_advisory_committee", label: "Advisory Committee" },
    { key: "de_novo_number", label: "De Novo Number" },
    { key: "appl_no", label: "Application No." },
    { key: "product_no", label: "Product No." },
    { key: "nct_id", label: "NCT ID" },
    { key: "trial_id", label: "Trial ID" },
    { key: "phase", label: "Phase" },
    { key: "status", label: "Status" },
    { key: "trade_name", label: "Trade Name" },
    { key: "ingredient", label: "Ingredient" },
    { key: "strength", label: "Strength" },
    { key: "route", label: "Route / Dosage Form" },
    { key: "df_route", label: "Route / Dosage Form" },
    { key: "appl_type", label: "Application Type" },
    { key: "te_code", label: "TE Code" },
    { key: "exclusivity_code", label: "Exclusivity" },
    { key: "patent_no", label: "Patent No." },
    { key: "patent_expire_date", label: "Patent Expiry" },
    { key: "delist_flag", label: "Delisted" },
    { key: "date_received", label: "Date Received" },
    { key: "decision_date", label: "Decision Date" },
    { key: "time_to_certify_days", label: "Days to Certify" },
    { key: "condition", label: "Condition" },
    { key: "intervention", label: "Intervention" },
    { key: "country", label: "Country" },
    { key: "continent", label: "Continent" },
    { key: "publication_date", label: "Published" },
    { key: "tags", label: "Tags" },
  ];

  protected metaEntries(r: SearchResult): { key: string; label: string; value: string }[] {
    const meta = (r.metadata ?? {}) as Record<string, unknown>;
    const out: { key: string; label: string; value: string }[] = [];
    const seenLabels = new Set<string>();
    for (const f of ResultsTableComponent.META_FIELDS) {
      if (seenLabels.has(f.label)) continue;
      const raw = meta[f.key];
      if (raw === undefined || raw === null) continue;
      let val: string;
      if (Array.isArray(raw)) {
        val = raw.filter((x) => x !== null && x !== undefined && `${x}`.trim() !== "").join(", ");
      } else if (typeof raw === "boolean") {
        val = raw ? "Yes" : "No";
      } else {
        val = String(raw);
      }
      val = val.trim();
      if (!val || /^(unknown|n\/a|none|null)$/i.test(val)) continue;
      out.push({ key: f.key, label: f.label, value: val });
      seenLabels.add(f.label);
    }
    return out;
  }
}
