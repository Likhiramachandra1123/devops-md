import { CommonModule } from "@angular/common";
import { Component, input } from "@angular/core";
import { LucideAngularModule, BookOpen, Database, FileText, Sparkles } from "lucide-angular";
import { SourceType } from "../../models/types";

@Component({
  selector: "app-source-badge",
  standalone: true,
  imports: [CommonModule, LucideAngularModule],
  template: `
    @switch (sourceType()) {
      @case ('knowledge_base') {
        <span class="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700 ring-1 ring-emerald-200">
          <lucide-icon [img]="Database" class="h-3 w-3"></lucide-icon>
          From knowledge base
          @if (citationCount() > 0) { · {{ citationCount() }} source{{ citationCount() === 1 ? '' : 's' }} }
        </span>
      }
      @case ('uploaded_document') {
        <span class="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-2.5 py-1 text-[11px] font-medium text-brand-700 ring-1 ring-brand-200">
          <lucide-icon [img]="FileText" class="h-3 w-3"></lucide-icon>
          From uploaded document
          @if (filename()) { · {{ filename() }} }
        </span>
      }
      @case ('general_knowledge') {
        <span class="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-medium text-amber-800 ring-1 ring-amber-200">
          <lucide-icon [img]="Sparkles" class="h-3 w-3"></lucide-icon>
          From general knowledge · not in KB
        </span>
      }
      @default {
        <span class="inline-flex items-center gap-1.5 rounded-full bg-ink-100 px-2.5 py-1 text-[11px] font-medium text-ink-600 ring-1 ring-ink-200">
          <lucide-icon [img]="BookOpen" class="h-3 w-3"></lucide-icon>
          No source
        </span>
      }
    }
  `,
})
export class SourceBadgeComponent {
  sourceType = input<SourceType>("none");
  citationCount = input<number>(0);
  filename = input<string | undefined>(undefined);

  protected readonly Database = Database;
  protected readonly FileText = FileText;
  protected readonly Sparkles = Sparkles;
  protected readonly BookOpen = BookOpen;
}
