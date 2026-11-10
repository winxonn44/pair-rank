import { Component, input, output } from '@angular/core';
import { Answer, Question } from '../models';

@Component({
  selector: 'app-question-card',
  templateUrl: './question-card.html',
  styleUrl: './question-card.css',
  host: { '(window:keydown)': 'onKey($event)' },
})
export class QuestionCard {
  readonly newPlace = input.required<string>();
  readonly question = input.required<Question>();
  readonly disabled = input(false);

  readonly answered = output<Answer>();
  readonly cancelled = output();

  answer(answer: Answer): void {
    if (!this.disabled()) {
      this.answered.emit(answer);
    }
  }

  onKey(event: KeyboardEvent): void {
    const typing = event.target instanceof HTMLInputElement;
    if (typing || event.repeat || event.altKey || event.ctrlKey || event.metaKey) {
      return;
    }
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      this.answer(event.key === 'ArrowLeft' ? 'better' : 'worse');
    }
  }
}
