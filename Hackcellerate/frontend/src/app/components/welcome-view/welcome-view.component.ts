import { CommonModule } from "@angular/common";
import { Component, EventEmitter, Output } from "@angular/core";
import { LucideAngularModule, Sparkles } from "lucide-angular";
import { ComposerComponent, SendPayload } from "../composer/composer.component";
import { QuickAction, QuickActionsComponent } from "../quick-actions/quick-actions.component";

@Component({
  selector: "app-welcome-view",
  standalone: true,
  imports: [CommonModule, LucideAngularModule, ComposerComponent, QuickActionsComponent],
  host: { class: "block h-full min-h-0" },
  template: `
    <div class="flex h-full items-center justify-center overflow-y-auto px-6 py-12">
      <div class="w-full max-w-3xl">
        <div class="mb-6 flex items-center justify-center">
          <div class="flex items-center gap-2 rounded-full border border-brand-100 bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700">
            <lucide-icon [img]="Sparkles" class="h-3.5 w-3.5"></lucide-icon>
            RegView · Regulatory Research Assistant
          </div>
        </div>
        <h1 class="mb-2 text-center text-3xl font-semibold tracking-tight text-ink-900 sm:text-4xl">
          What can I help you with?
        </h1>
        <p class="mx-auto mb-8 max-w-xl text-center text-sm text-ink-500">
          Ask a question, run a structured search across the knowledge base, or attach a document
          to ask questions grounded in its content.
        </p>

        <div class="rounded-2xl border border-ink-200 bg-white p-3 shadow-panel">
          <app-composer
            [size]="'lg'"
            [placeholder]="'Ask about openFDA data, clinical trials, recalls, or attach a PDF…'"
            (send)="send.emit($event)"
          ></app-composer>
        </div>

        <div class="mt-6 flex flex-col items-center gap-3">
          <div class="text-[11px] font-semibold uppercase tracking-wider text-ink-400">Try one of these</div>
          <app-quick-actions (pick)="onPick($event)"></app-quick-actions>
        </div>
      </div>
    </div>
  `,
})
export class WelcomeViewComponent {
  @Output() send = new EventEmitter<SendPayload>();
  @Output() pickAction = new EventEmitter<QuickAction>();

  protected readonly Sparkles = Sparkles;

  protected onPick(a: QuickAction) {
    if (a.prompt) {
      this.send.emit({ message: a.prompt, mode: a.mode, file: null });
    } else {
      this.pickAction.emit(a);
    }
  }
}
