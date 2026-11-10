import {
  Component,
  ElementRef,
  Injector,
  OnInit,
  afterNextRender,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiError, ApiService } from '../api.service';
import { Answer, InsertionStep, Question, RankList } from '../models';
import { QuestionCard } from '../question-card/question-card';
import { RankedList } from '../ranked-list/ranked-list';

const LIST_NAME = 'My LA places';

interface ActiveInsertion {
  id: number;
  placeName: string;
  question: Question;
}

/** Each of these means the insertion on screen no longer exists on the server. */
const STALE_MESSAGES: Readonly<Record<string, string>> = {
  list_changed: "Your list changed in another tab, so this place wasn't added. Add it again.",
  insertion_closed: 'This place is no longer being added. Add it again.',
  question_out_of_order: 'That question is out of date. Add the place again.',
  answer_mismatch: 'That question was already answered differently. Add the place again.',
};

function messageFor(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return 'Something went wrong. Reload the page and try again.';
  }
  if (error.code === 'already_ranked') {
    return 'That place is already on your list.';
  }
  if (error.code && error.code in STALE_MESSAGES) {
    return STALE_MESSAGES[error.code];
  }
  if (error.status === 400) {
    return 'Enter a restaurant name of up to 120 characters.';
  }
  if (error.status === 429) {
    return 'Too many requests. Wait a minute and try again.';
  }
  return "The server didn't respond. Check that it's running and try again.";
}

@Component({
  selector: 'app-rank-page',
  imports: [QuestionCard, RankedList],
  templateUrl: './rank-page.html',
  styleUrl: './rank-page.css',
})
export class RankPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly injector = inject(Injector);
  private readonly placeInput = viewChild<ElementRef<HTMLInputElement>>('placeInput');
  private questionShownAt = 0;

  readonly list = signal<RankList | null>(null);
  readonly active = signal<ActiveInsertion | null>(null);
  readonly draft = signal('');
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly placedPosition = signal<number | null>(null);

  readonly entries = computed(() => this.list()?.entries ?? []);
  readonly comparingPosition = computed(() => this.active()?.question.ref_position ?? null);

  ngOnInit(): Promise<void> {
    return this.run(async () => {
      const lists = await firstValueFrom(this.api.getLists());
      if (lists.length > 0) {
        this.list.set(await firstValueFrom(this.api.getList(lists[0].id)));
      }
    });
  }

  onDraft(event: Event): void {
    this.draft.set((event.target as HTMLInputElement).value);
  }

  add(event: Event): Promise<void> {
    event.preventDefault();
    const placeName = this.draft().trim();
    if (!placeName) {
      return Promise.resolve();
    }
    return this.run(async () => {
      const list = this.list() ?? (await firstValueFrom(this.api.createList(LIST_NAME)));
      this.list.set(list);
      const step = await firstValueFrom(this.api.startInsertion(list.id, placeName));
      this.show(step, step.insertion_id, placeName);
    });
  }

  answer(answer: Answer): Promise<void> {
    const active = this.active();
    if (!active) {
      return Promise.resolve();
    }
    const responseMs = Math.round(performance.now() - this.questionShownAt);
    return this.run(async () => {
      const step = await firstValueFrom(
        this.api.answer(active.id, active.question.index, answer, responseMs),
      );
      this.show(step, active.id, active.placeName);
    });
  }

  cancel(): Promise<void> {
    const active = this.active();
    if (!active) {
      return Promise.resolve();
    }
    return this.run(async () => {
      await firstValueFrom(this.api.abandon(active.id));
      this.active.set(null);
      this.focusInput();
    });
  }

  private show(step: InsertionStep, insertionId: number, placeName: string): void {
    this.notice.set(null);
    if (step.done) {
      this.list.set(step.list);
      this.active.set(null);
      this.draft.set('');
      this.placedPosition.set(step.position);
      this.notice.set(`${placeName} is now number ${step.position + 1}.`);
      this.focusInput();
    } else {
      this.placedPosition.set(null);
      this.active.set({ id: insertionId, placeName, question: step.question });
      this.questionShownAt = performance.now();
    }
  }

  private focusInput(): void {
    afterNextRender(() => this.placeInput()?.nativeElement.focus(), { injector: this.injector });
  }

  /** One request at a time, so a double press can't send a second answer. */
  private async run(action: () => Promise<void>): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    try {
      await action();
    } catch (error) {
      this.error.set(messageFor(error));
      if (error instanceof ApiError && error.code && error.code in STALE_MESSAGES) {
        await this.reload();
      }
    } finally {
      this.busy.set(false);
    }
  }

  private async reload(): Promise<void> {
    this.active.set(null);
    const list = this.list();
    if (list) {
      this.list.set(await firstValueFrom(this.api.getList(list.id)));
    }
  }
}
