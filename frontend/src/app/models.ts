/** Hand-written to match the JSON built in backend/ranking/services.py. */

export interface Place {
  id: number;
  name: string;
  city: string;
}

export type Tier = 'liked' | 'fine' | 'disliked';

export interface RankedEntry {
  place: Place;
  /** 0 is the best place on the list. */
  position: number;
  /** 0–10, computed by the server from the position. */
  score: number;
  tier: Tier | null;
}

export interface ListSummary {
  id: number;
  name: string;
  version: number;
}

export interface RankList extends ListSummary {
  entries: RankedEntry[];
}

export interface Question {
  index: number;
  ref_place: Place;
  ref_position: number;
}

export interface QuestionStep {
  /** Only present when the insertion starts. Later questions omit it. */
  insertion_id?: number;
  question: Question;
  done?: undefined;
}

export interface DoneStep {
  insertion_id?: number;
  done: true;
  position: number;
  list: RankList;
}

/** What the server sends after an answer. */
export type InsertionStep = QuestionStep | DoneStep;

/** What the server sends when an insertion starts, which always names it. */
export type StartedStep = InsertionStep & { insertion_id: number };

/** How the new place compares with the place in the question. */
export type Answer = 'better' | 'worse';
