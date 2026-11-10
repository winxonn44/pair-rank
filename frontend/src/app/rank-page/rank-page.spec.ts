import { TestBed } from '@angular/core/testing';
import { Observable, of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { ApiError, ApiService } from '../api.service';
import { DoneStep, QuestionStep, RankList, StartedStep } from '../models';
import { RankPage } from './rank-page';

const emptyList: RankList = { id: 5, name: 'My LA places', version: 0, entries: [] };
const oneEntry: RankList = {
  ...emptyList,
  version: 1,
  entries: [{ place: { id: 1, name: 'Sqirl', city: 'LA' }, position: 0, score: 10, tier: null }],
};
const question: StartedStep = {
  insertion_id: 9,
  question: { index: 0, ref_position: 0, ref_place: { id: 1, name: 'Sqirl', city: 'LA' } },
};
const done = (list: RankList, position: number): DoneStep => ({ done: true, position, list });
const fail = (status: number, code: string | null): Observable<never> =>
  throwError(() => new ApiError(status, code));

describe('RankPage', () => {
  const api = {
    getLists: vi.fn(),
    getList: vi.fn(),
    createList: vi.fn(),
    startInsertion: vi.fn(),
    answer: vi.fn(),
    abandon: vi.fn(),
  };

  const create = async () => {
    const fixture = TestBed.createComponent(RankPage);
    const page = fixture.componentInstance;
    // The page's work runs on promises, which whenStable doesn't wait for.
    const settle = async () => {
      await new Promise((resolve) => setTimeout(resolve));
      fixture.detectChanges();
    };
    fixture.detectChanges();
    await settle();
    const addPlace = async (name: string) => {
      page.draft.set(name);
      await page.add(new Event('submit'));
      await settle();
    };
    const text = () => fixture.nativeElement.textContent as string;
    return { fixture, page, settle, addPlace, text };
  };

  beforeEach(() => {
    vi.resetAllMocks();
    api.getLists.mockReturnValue(of([]));
    api.getList.mockReturnValue(of(oneEntry));
    api.createList.mockReturnValue(of(emptyList));
    TestBed.configureTestingModule({ providers: [{ provide: ApiService, useValue: api }] });
  });

  it('starts empty and creates no list until a place is added', async () => {
    const { text } = await create();
    expect(text()).toContain('Add one place to start');
    expect(api.createList).not.toHaveBeenCalled();
  });

  it('reopens the list this browser already has', async () => {
    api.getLists.mockReturnValue(of([{ id: 5, name: 'x', version: 1 }]));
    const { text } = await create();
    expect(api.getList).toHaveBeenCalledWith(5);
    expect(text()).toContain('Sqirl');
  });

  it('places the first restaurant without a question', async () => {
    api.startInsertion.mockReturnValue(of(done(oneEntry, 0)));
    const { page, addPlace, text } = await create();
    await addPlace('  Sqirl ');
    expect(api.startInsertion).toHaveBeenCalledWith(5, 'Sqirl');
    expect(text()).toContain('Sqirl is now number 1.');
    expect(page.draft()).toBe('');
    expect(page.placedPosition()).toBe(0);
  });

  it('ignores a blank name', async () => {
    const { addPlace } = await create();
    await addPlace('   ');
    expect(api.createList).not.toHaveBeenCalled();
  });

  it('runs a question through to a placement and highlights the compared row', async () => {
    api.getLists.mockReturnValue(of([{ id: 5, name: 'x', version: 1 }]));
    api.startInsertion.mockReturnValue(of(question));
    const after: RankList = {
      ...oneEntry,
      version: 2,
      entries: [
        { place: { id: 2, name: 'Bestia', city: 'LA' }, position: 0, score: 10, tier: null },
        { ...oneEntry.entries[0], position: 1, score: 0 },
      ],
    };
    api.answer.mockReturnValue(of(done(after, 0)));
    const { fixture, page, settle, addPlace, text } = await create();
    await addPlace('Bestia');

    expect(text()).toContain('Question 1');
    expect(fixture.nativeElement.querySelector('li.comparing')?.textContent).toContain('Sqirl');

    await page.answer('better');
    await settle();
    expect(api.answer).toHaveBeenCalledWith(9, 0, 'better', expect.any(Number));
    expect(page.active()).toBeNull();
    expect(text()).toContain('Bestia is now number 1.');
    expect(fixture.nativeElement.querySelector('li.comparing')).toBeNull();
  });

  it('keeps using the insertion id for questions that do not repeat it', async () => {
    api.getLists.mockReturnValue(of([{ id: 5, name: 'x', version: 1 }]));
    api.startInsertion.mockReturnValue(of(question));
    const second: QuestionStep = {
      question: { index: 1, ref_position: 0, ref_place: { id: 1, name: 'Sqirl', city: 'LA' } },
    };
    api.answer.mockReturnValueOnce(of(second)).mockReturnValueOnce(of(done(oneEntry, 0)));
    const { page, settle, addPlace, text } = await create();
    await addPlace('Bestia');
    await page.answer('better');
    await settle();
    expect(text()).toContain('Question 2');
    await page.answer('worse');
    expect(api.answer).toHaveBeenLastCalledWith(9, 1, 'worse', expect.any(Number));
  });

  it('sends one answer when a second press arrives during the first', async () => {
    api.getLists.mockReturnValue(of([{ id: 5, name: 'x', version: 1 }]));
    api.startInsertion.mockReturnValue(of(question));
    api.answer.mockReturnValue(of(done(oneEntry, 0)));
    const { page, addPlace } = await create();
    await addPlace('Bestia');
    await Promise.all([page.answer('better'), page.answer('better')]);
    expect(api.answer).toHaveBeenCalledOnce();
  });

  it('explains a duplicate and keeps the typed name', async () => {
    api.startInsertion.mockReturnValue(fail(409, 'already_ranked'));
    const { page, addPlace, text } = await create();
    await addPlace('Sqirl');
    expect(text()).toContain('already on your list');
    expect(page.draft()).toBe('Sqirl');
    expect(page.busy()).toBe(false);
  });

  it('reloads the list and leaves the question when the list changed elsewhere', async () => {
    api.getLists.mockReturnValue(of([{ id: 5, name: 'x', version: 1 }]));
    api.startInsertion.mockReturnValue(of(question));
    api.answer.mockReturnValue(fail(409, 'list_changed'));
    const { page, settle, addPlace, text } = await create();
    await addPlace('Bestia');
    api.getList.mockClear();
    await page.answer('worse');
    await settle();
    expect(api.getList).toHaveBeenCalledWith(5);
    expect(page.active()).toBeNull();
    expect(text()).toContain('changed in another tab');
  });

  it('abandons on stop and returns to the form', async () => {
    api.getLists.mockReturnValue(of([{ id: 5, name: 'x', version: 1 }]));
    api.startInsertion.mockReturnValue(of(question));
    api.abandon.mockReturnValue(of(undefined));
    const { fixture, page, settle, addPlace } = await create();
    await addPlace('Bestia');
    await page.cancel();
    await settle();
    expect(api.abandon).toHaveBeenCalledWith(9);
    expect(fixture.nativeElement.querySelector('form')).not.toBeNull();
  });

  it('says when the server cannot be reached', async () => {
    api.getLists.mockReturnValue(fail(0, null));
    const { text } = await create();
    expect(text()).toContain("server didn't respond");
  });
});
