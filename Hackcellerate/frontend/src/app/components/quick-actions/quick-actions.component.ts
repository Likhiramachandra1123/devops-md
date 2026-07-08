import { CommonModule } from "@angular/common";
import { Component, EventEmitter, Output, input } from "@angular/core";
import { LucideAngularModule, BookOpen, Database, Globe, Layers, MapPin, Microscope } from "lucide-angular";

export interface QuickAction {
  id: string;
  label: string;
  icon: any;
  prompt: string;
  mode: "chat" | "search";
}

@Component({
  selector: "app-quick-actions",
  standalone: true,
  imports: [CommonModule, LucideAngularModule],
  template: `
    <div class="flex flex-wrap gap-2">
      @for (a of actions; track a.id) {
        <button
          type="button"
          (click)="pick.emit(a)"
          class="inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-white font-medium text-brand-700 shadow-sm transition hover:border-brand-300 hover:bg-brand-50"
          [ngClass]="sizeClass()"
        >
          <lucide-icon [img]="a.icon" class="h-3.5 w-3.5 text-brand-600"></lucide-icon>
          {{ a.label }}
        </button>
      }
    </div>
  `,
})
export class QuickActionsComponent {
  size = input<"sm" | "md">("md");
  @Output() pick = new EventEmitter<QuickAction>();

  protected readonly actions: QuickAction[] = [
    { id: "find-cancer", label: "Find Cancer Studies", icon: Microscope, prompt: "Find recent clinical studies on cancer treatments and outcomes", mode: "search" },
    { id: "general", label: "General Question", icon: BookOpen, prompt: "", mode: "chat" },
    { id: "by-region", label: "By Region", icon: MapPin, prompt: "Show regulatory findings by geographic region", mode: "search" },
    { id: "by-source", label: "By Data Source", icon: Database, prompt: "Filter results by data source (openFDA, ClinicalTrials.gov, Orange Book)", mode: "search" },
    { id: "longitudinal", label: "Longitudinality", icon: Layers, prompt: "Longitudinal drug safety and outcome data", mode: "search" },
    { id: "recalls", label: "Recalls & Enforcement", icon: Globe, prompt: "Recent drug and device recalls with severity classifications", mode: "search" },
  ];

  protected sizeClass(): string {
    return this.size() === "sm" ? "text-[11px] px-2.5 py-1" : "text-xs px-3 py-1.5";
  }
}
