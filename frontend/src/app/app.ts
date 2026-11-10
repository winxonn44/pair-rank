import { Component } from '@angular/core';
import { RankPage } from './rank-page/rank-page';

@Component({
  selector: 'app-root',
  imports: [RankPage],
  template: '<app-rank-page />',
})
export class App {}
