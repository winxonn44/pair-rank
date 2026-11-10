import { DecimalPipe } from '@angular/common';
import { Component, input } from '@angular/core';
import { RankedEntry } from '../models';

@Component({
  selector: 'app-ranked-list',
  imports: [DecimalPipe],
  templateUrl: './ranked-list.html',
  styleUrl: './ranked-list.css',
})
export class RankedList {
  readonly entries = input.required<RankedEntry[]>();
  /** The row the current question is about. */
  readonly comparingPosition = input<number | null>(null);
  /** The row that was just added. */
  readonly placedPosition = input<number | null>(null);
}
