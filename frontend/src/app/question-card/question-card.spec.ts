import { ComponentFixture, TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { Answer } from '../models';
import { QuestionCard } from './question-card';

describe('QuestionCard', () => {
  let fixture: ComponentFixture<QuestionCard>;
  let answers: Answer[];

  const press = (key: string, init: KeyboardEventInit = {}): KeyboardEvent => {
    const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init });
    window.dispatchEvent(event);
    return event;
  };
  const buttons = (): HTMLButtonElement[] =>
    Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('button'));

  beforeEach(() => {
    fixture = TestBed.createComponent(QuestionCard);
    fixture.componentRef.setInput('newPlace', 'Bestia');
    fixture.componentRef.setInput('question', {
      index: 2,
      ref_position: 1,
      ref_place: { id: 1, name: 'Sqirl', city: 'Los Angeles' },
    });
    answers = [];
    fixture.componentInstance.answered.subscribe((answer) => answers.push(answer));
    fixture.detectChanges();
  });

  it('names both places and counts from one', () => {
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Bestia');
    expect(text).toContain('Sqirl');
    expect(text).toContain('Question 3');
  });

  it('emits the answer for each button', () => {
    buttons()[0].click();
    buttons()[1].click();
    expect(answers).toEqual(['better', 'worse']);
  });

  it('maps left to better and right to worse', () => {
    expect(press('ArrowLeft').defaultPrevented).toBe(true);
    press('ArrowRight');
    expect(answers).toEqual(['better', 'worse']);
  });

  it('ignores other keys, a held key, and browser shortcuts', () => {
    press('Enter');
    press('ArrowLeft', { repeat: true });
    press('ArrowLeft', { metaKey: true });
    expect(answers).toEqual([]);
  });

  it('ignores arrows typed inside a text field', () => {
    const field = document.createElement('input');
    document.body.append(field);
    field.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
    field.remove();
    expect(answers).toEqual([]);
  });

  it('emits nothing while disabled', () => {
    fixture.componentRef.setInput('disabled', true);
    fixture.detectChanges();
    press('ArrowLeft');
    buttons()[0].click();
    expect(answers).toEqual([]);
  });

  it('stops listening once removed', () => {
    const spy = vi.fn();
    fixture.componentInstance.answered.subscribe(spy);
    fixture.destroy();
    press('ArrowLeft');
    expect(spy).not.toHaveBeenCalled();
  });

  it('emits cancelled from the stop button', () => {
    const spy = vi.fn();
    fixture.componentInstance.cancelled.subscribe(spy);
    buttons()[2].click();
    expect(spy).toHaveBeenCalledOnce();
  });
});
