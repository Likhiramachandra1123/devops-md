import { CommonModule } from "@angular/common";
import { Component, ElementRef, EventEmitter, NgZone, OnDestroy, Output, ViewChild, inject, input, signal } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { LucideAngularModule, Mic, MicOff, Paperclip, Search, SendHorizontal, X } from "lucide-angular";

export interface SendPayload {
  message: string;
  mode: "chat" | "search";
  file: File | null;
}

const ACCEPT =
  ".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain";

type SpeechRecognitionCtor = new () => any;

function getSpeechRecognition(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as any;
  return (w.SpeechRecognition || w.webkitSpeechRecognition) ?? null;
}

@Component({
  selector: "app-composer",
  standalone: true,
  imports: [CommonModule, FormsModule, LucideAngularModule],
  template: `
    <div class="w-full">
      @if (file()) {
        <div class="mb-2 inline-flex items-center gap-2 rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs text-brand-800">
          <lucide-icon [img]="Paperclip" class="h-3.5 w-3.5"></lucide-icon>
          <span class="max-w-[220px] truncate font-medium">{{ file()!.name }}</span>
          <span class="text-brand-500">· {{ formatBytes(file()!.size) }}</span>
          <button
            type="button"
            (click)="clearFile()"
            class="ml-1 rounded-full p-0.5 text-brand-500 hover:bg-brand-100 hover:text-brand-700"
            title="Remove attachment"
          >
            <lucide-icon [img]="X" class="h-3.5 w-3.5"></lucide-icon>
          </button>
        </div>
      }

      <div
        class="flex items-end gap-2 rounded-2xl border border-ink-200 bg-white shadow-panel focus-within:border-brand-400 focus-within:ring-2 focus-within:ring-brand-100"
        [ngClass]="padClass()"
      >
        <button
          type="button"
          [title]="file() ? 'Replace attachment' : 'Attach a document (PDF / DOCX / TXT)'"
          (click)="fileInput.click()"
          class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-ink-500 transition hover:bg-ink-100 hover:text-ink-700"
        >
          <lucide-icon [img]="Paperclip" class="h-4 w-4"></lucide-icon>
        </button>
        <input
          #fileInput
          type="file"
          class="hidden"
          [accept]="ACCEPT"
          (change)="onFileChosen($event)"
        />

        <textarea
          #textArea
          [(ngModel)]="text"
          (keydown)="onKeyDown($event)"
          [placeholder]="file() ? 'Ask about ' + file()!.name + '…' : placeholder()"
          rows="1"
          class="flex-1 resize-none border-0 bg-transparent px-1 py-1.5 text-sm text-ink-800 placeholder:text-ink-400 focus:outline-none"
          [ngClass]="heightClass()"
        ></textarea>

        <div class="flex shrink-0 items-center gap-1">
          <button
            type="button"
            [title]="micTitle()"
            [disabled]="!speechSupported"
            (click)="toggleMic()"
            [ngClass]="{
              'text-red-600 hover:bg-red-50 animate-pulse': listening(),
              'text-ink-500 hover:bg-ink-100 hover:text-ink-700': speechSupported && !listening(),
              'text-ink-300 cursor-not-allowed': !speechSupported
            }"
            class="flex h-8 w-8 items-center justify-center rounded-md transition"
          >
            <lucide-icon [img]="listening() ? MicOff : Mic" class="h-4 w-4"></lucide-icon>
          </button>
          <button
            type="button"
            title="Structured search — results in table"
            (click)="submit('search')"
            [disabled]="loading() || !text.trim()"
            class="flex h-8 w-8 items-center justify-center rounded-md text-brand-600 transition hover:bg-brand-50 disabled:cursor-not-allowed disabled:text-ink-300 disabled:hover:bg-transparent"
          >
            <lucide-icon [img]="Search" class="h-4 w-4"></lucide-icon>
          </button>
          <button
            type="button"
            title="Send (Enter)"
            (click)="submit('chat')"
            [disabled]="loading() || !text.trim()"
            class="flex h-9 items-center gap-1.5 rounded-lg bg-brand-600 px-3 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-ink-200 disabled:text-ink-400"
          >
            <lucide-icon [img]="SendHorizontal" class="h-4 w-4"></lucide-icon>
            <span class="hidden sm:inline">Send</span>
          </button>
        </div>
      </div>
      <div class="mt-1.5 text-[11px] text-ink-400">
        <span class="font-medium text-ink-500">Enter</span> to send ·
        <span class="font-medium text-ink-500">Shift+Enter</span> for new line · click
        <span class="font-medium text-ink-500">search icon</span> for tabular results
        @if (listening()) {
          · <span class="font-medium text-red-600">● Listening…</span>
        }
        @if (micError()) {
          · <span class="font-medium text-red-600">{{ micError() }}</span>
        }
      </div>
    </div>
  `,
})
export class ComposerComponent implements OnDestroy {
  loading = input<boolean>(false);
  placeholder = input<string>("Ask me about research data…");
  size = input<"sm" | "md" | "lg">("md");

  @Output() send = new EventEmitter<SendPayload>();

  @ViewChild("textArea") textArea?: ElementRef<HTMLTextAreaElement>;

  protected text = "";
  protected readonly file = signal<File | null>(null);
  protected readonly ACCEPT = ACCEPT;

  protected readonly Paperclip = Paperclip;
  protected readonly Mic = Mic;
  protected readonly MicOff = MicOff;
  protected readonly Search = Search;
  protected readonly SendHorizontal = SendHorizontal;
  protected readonly X = X;

  // ── Voice input (Web Speech API) ────────────────────────────────
  private readonly zone = inject(NgZone);
  private readonly SR = getSpeechRecognition();
  protected readonly speechSupported = !!this.SR;
  protected readonly listening = signal<boolean>(false);
  protected readonly micError = signal<string | null>(null);
  private recognition: any = null;
  private baseText = "";

  protected micTitle(): string {
    if (!this.speechSupported) return "Voice input not supported in this browser (try Chrome or Edge)";
    return this.listening() ? "Stop listening" : "Start voice input";
  }

  protected toggleMic() {
    if (!this.speechSupported) return;
    if (this.listening()) {
      this.stopMic();
    } else {
      this.startMic();
    }
  }

  private startMic() {
    try {
      const rec = new (this.SR as SpeechRecognitionCtor)();
      rec.lang = navigator.language || "en-US";
      rec.continuous = true;
      rec.interimResults = true;

      this.baseText = this.text ? this.text.replace(/\s+$/, "") + " " : "";
      this.micError.set(null);

      rec.onresult = (event: any) => {
        let interim = "";
        let finalText = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const res = event.results[i];
          if (res.isFinal) {
            finalText += res[0].transcript;
          } else {
            interim += res[0].transcript;
          }
        }
        this.zone.run(() => {
          if (finalText) {
            this.baseText = (this.baseText + finalText).replace(/\s+/g, " ");
            if (!this.baseText.endsWith(" ")) this.baseText += " ";
          }
          this.text = (this.baseText + interim).replace(/\s+/g, " ").trimStart();
        });
      };

      rec.onerror = (event: any) => {
        const code = event?.error ?? "error";
        const msg =
          code === "not-allowed" || code === "service-not-allowed"
            ? "Microphone access denied"
            : code === "no-speech"
            ? "No speech detected"
            : code === "audio-capture"
            ? "No microphone found"
            : `Speech error: ${code}`;
        this.zone.run(() => this.micError.set(msg));
      };

      rec.onend = () => {
        this.zone.run(() => this.listening.set(false));
      };

      this.recognition = rec;
      rec.start();
      this.listening.set(true);
      // Focus the textarea so the user sees the transcript stream in.
      setTimeout(() => this.textArea?.nativeElement.focus(), 0);
    } catch (e: any) {
      this.micError.set(e?.message ?? "Failed to start voice input");
      this.listening.set(false);
    }
  }

  private stopMic() {
    try {
      this.recognition?.stop();
    } catch {
      /* ignore */
    }
    this.listening.set(false);
  }

  ngOnDestroy(): void {
    this.stopMic();
    this.recognition = null;
  }

  protected heightClass(): string {
    switch (this.size()) {
      case "lg":
        return "min-h-[68px]";
      case "sm":
        return "min-h-[36px]";
      default:
        return "min-h-[48px]";
    }
  }

  protected padClass(): string {
    return this.size() === "lg" ? "p-4" : "p-3";
  }

  protected onFileChosen(evt: Event) {
    const input = evt.target as HTMLInputElement;
    const f = input.files?.[0] ?? null;
    this.file.set(f);
    input.value = "";
  }

  protected clearFile() {
    this.file.set(null);
  }

  protected onKeyDown(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      this.submit("chat");
    }
  }

  protected submit(mode: "chat" | "search") {
    const trimmed = this.text.trim();
    if (!trimmed || this.loading()) return;
    if (this.listening()) this.stopMic();
    this.send.emit({ message: trimmed, mode, file: this.file() });
    this.text = "";
    this.baseText = "";
    this.file.set(null);
  }

  protected formatBytes(n: number): string {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  }
}
