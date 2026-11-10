import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RankedEntry } from '../models';
import { RankedList } from './ranked-list';

const entry = (position: number, name: string, score: number): RankedEntry => ({
  place: { id: position + 1, name, city: 'Los Angeles' },
  position,
  score,
  tier: null,
});

describe('RankedList', () => {
  let fixture: ComponentFixture<RankedList>;
  const rows = (): HTMLElement[] =>
    Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('li'));

  beforeEach(() => {
    fixture = TestBed.createComponent(RankedList);
    fixture.componentRef.setInput('entries', [entry(0, 'Bestia', 10), entry(1, 'Sqirl', 3.3333)]);
    fixture.detectChanges();
  });

  it('shows rank from one and scores to one decimal', () => {
    expect(rows()[0].querySelector('.rank')?.textContent).toBe('1');
    expect(rows()[0].querySelector('.score')?.textContent).toBe('10.0');
    expect(rows()[1].querySelector('.score')?.textContent).toBe('3.3');
  });

  it('marks only the row being compared', () => {
    fixture.componentRef.setInput('comparingPosition', 1);
    fixture.detectChanges();
    expect(rows().map((row) => row.classList.contains('comparing'))).toEqual([false, true]);
  });

  it('treats position 0 as a real position, not as nothing', () => {
    fixture.componentRef.setInput('comparingPosition', 0);
    fixture.detectChanges();
    expect(rows()[0].classList.contains('comparing')).toBe(true);
  });
});
