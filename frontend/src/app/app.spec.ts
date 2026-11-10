import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ApiService } from './api.service';
import { App } from './app';

describe('App', () => {
  it('renders the ranking page', () => {
    TestBed.configureTestingModule({
      providers: [{ provide: ApiService, useValue: { getLists: () => of([]) } }],
    });
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('h1')?.textContent).toContain('Rank the places');
  });
});
