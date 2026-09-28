import unittest
from tests.test_forecast import _result
from ironbound_rankings.models import PlayerIdentity, LeagueMatchup
from ironbound_rankings.weekly_forecast import attach_weekly_matchup_forecast, optimal_projected_lineup


class WeeklyLegalityTests(unittest.TestCase):
    def test_reserve_taxi_and_unavailable_players_are_not_selected(self):
        result = _result()
        result.league.roster_positions = ['QB']
        result.league.matchups = [LeagueMatchup(1, 1, 1, 2)]
        result.league.teams[0].player_ids = ['active', 'reserve', 'taxi', 'out']
        result.league.teams[0].reserve_player_ids = ['reserve']
        result.league.teams[0].taxi_player_ids = ['taxi']
        result.league.teams[1].player_ids = ['other']
        players = {p: PlayerIdentity(p, p, p, 'QB') for p in ['active', 'reserve', 'taxi', 'out', 'other']}
        projections = {p: {'pts': 99 if p in ['reserve', 'taxi', 'out'] else 20} for p in players}
        attach_weekly_matchup_forecast(result, players, projections, simulations=100,
                                      unavailable_player_ids={'out'})
        row = result.weekly_matchup_forecast[0]
        self.assertEqual(row['optimal_lineup_one'], ['active'])
        self.assertEqual(row['projection_fetched_at'], result.generated_at)
        self.assertIn('independent', row['uncertainty_note'])

    def test_duplicate_ids_cannot_fill_multiple_slots(self):
        players = {'a': PlayerIdentity('a', 'a', 'a', 'RB'), 'b': PlayerIdentity('b', 'b', 'b', 'RB')}
        lineup = optimal_projected_lineup(['a', 'a', 'b'], ['RB', 'FLEX'], players, {'a': 20, 'b': 10})
        self.assertEqual(set(lineup), {'a', 'b'})

    def test_availability_provider_preserves_questionable_but_excludes_out(self):
        from ironbound_rankings.sleeper import fetch_unavailable_players
        class Client:
            def get_json(self, url):
                return {'out': {'injury_status': 'Out'}, 'ir': {'status': 'IR'},
                        'q': {'injury_status': 'Questionable'}, 'active': {'status': 'Active'}}
        self.assertEqual(fetch_unavailable_players(Client()), {'out', 'ir'})

    def test_large_roster_optimization_fills_distinct_legal_slots(self):
        players = {str(i): PlayerIdentity(str(i), str(i), str(i), 'WR') for i in range(35)}
        lineup = optimal_projected_lineup(list(players), ['FLEX'] * 9, players,
                                         {str(i): float(i+1) for i in range(35)})
        self.assertEqual(set(lineup), {str(i) for i in range(26, 35)})
