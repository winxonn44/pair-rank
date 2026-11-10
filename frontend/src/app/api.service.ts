import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, throwError } from 'rxjs';
import { Answer, InsertionStep, ListSummary, RankList, StartedStep } from './models';

/** A failed request. `code` is the server's reason on a 409, such as `list_changed`. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string | null,
  ) {
    super(code ?? `request failed with status ${status}`);
    this.name = 'ApiError';
  }
}

function toApiError(response: HttpErrorResponse): ApiError {
  const code: unknown = response.status === 409 ? response.error?.code : null;
  return new ApiError(response.status, typeof code === 'string' ? code : null);
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  /** Also how a new browser receives the CSRF cookie its first POST needs. */
  getLists(): Observable<ListSummary[]> {
    return this.http.get<ListSummary[]>('/api/lists/').pipe(catchError(this.fail));
  }

  getList(id: number): Observable<RankList> {
    return this.http.get<RankList>(`/api/lists/${id}/`).pipe(catchError(this.fail));
  }

  createList(name: string): Observable<RankList> {
    return this.http.post<RankList>('/api/lists/', { name }).pipe(catchError(this.fail));
  }

  startInsertion(listId: number, placeName: string): Observable<StartedStep> {
    return this.http
      .post<StartedStep>(`/api/lists/${listId}/insertions/`, { place_name: placeName })
      .pipe(catchError(this.fail));
  }

  answer(
    insertionId: number,
    questionIndex: number,
    answer: Answer,
    responseMs: number,
  ): Observable<InsertionStep> {
    return this.http
      .post<InsertionStep>(`/api/insertions/${insertionId}/answers/`, {
        question_index: questionIndex,
        answer,
        response_ms: responseMs,
      })
      .pipe(catchError(this.fail));
  }

  abandon(insertionId: number): Observable<void> {
    return this.http
      .post<void>(`/api/insertions/${insertionId}/abandon/`, {})
      .pipe(catchError(this.fail));
  }

  private readonly fail = (response: HttpErrorResponse): Observable<never> =>
    throwError(() => toApiError(response));
}
