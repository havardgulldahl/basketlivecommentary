from dataclasses import dataclass
from typing import Optional, List, Dict
from datetime import datetime


@dataclass
class Player:
    """Player information."""

    id: int
    team_id: int
    first_name: str
    last_name: str
    shirt_no: Optional[int]
    is_coach: bool
    is_captain: bool
    is_starter: bool
    shoots: str
    birthday: Optional[str]
    picture_file_id: Optional[int]
    weight: Optional[float]
    height: Optional[float]

    @property
    def full_name(self) -> str:
        """Get player's full name."""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display_name(self) -> str:
        """Get player's display name with shirt number."""
        if self.shirt_no is not None:
            return f"#{self.shirt_no} {self.full_name}"
        return self.full_name


@dataclass
class Period:
    """Period/quarter information."""

    id: int
    name: str
    duration: int  # seconds
    is_active: bool
    is_overtime: bool
    is_shootout: bool
    sort_order: int
    time_ascending: bool


@dataclass
class Referee:
    """Referee information."""

    id: int
    name: str
    type: str


@dataclass
class MatchMetadata:
    """Complete match metadata."""

    match_id: int
    tournament_id: int
    tournament_name: str

    # Teams
    home_team_id: int
    away_team_id: int
    home_team_name: str
    away_team_name: str

    # Venue
    activity_area: str
    activity_area_id: int
    venue_id: int
    venue_no: str

    # Timing
    match_date: str
    match_start_time: Optional[str]

    # Rosters
    home_players: List[Player]
    away_players: List[Player]
    home_coaches: List[Player]
    away_coaches: List[Player]

    # Structure
    periods: List[Period]

    # Officials
    referees: List[Referee]

    # Other
    attendance: int
    live_arena: bool
    live_arena_status: int
    registration_mode: int

    def __post_init__(self):
        """Build lookup dictionaries after initialization."""
        self._player_lookup: Dict[int, Player] = {}
        self._build_lookups()

    def _build_lookups(self):
        """Build internal lookup dictionaries for fast access."""
        # Build player lookup by ID
        all_players = (
            self.home_players
            + self.away_players
            + self.home_coaches
            + self.away_coaches
        )
        for player in all_players:
            self._player_lookup[player.id] = player

    def get_player(self, player_id: int) -> Optional[Player]:
        """Get player by ID."""
        return self._player_lookup.get(player_id)

    def get_player_name(self, player_id: int) -> str:
        """Get player name by ID, with fallback."""
        player = self.get_player(player_id)
        if player:
            return player.full_name
        return f"Player {player_id}"

    def get_player_display_name(self, player_id: int) -> str:
        """Get player display name (with number) by ID."""
        player = self.get_player(player_id)
        if player:
            return player.display_name
        return f"Player {player_id}"

    def get_team_name(self, team_code: str) -> str:
        """Get team name from code (H/A)."""
        if team_code == "H":
            return self.home_team_name.strip()
        elif team_code == "A":
            return self.away_team_name.strip()
        return f"Team {team_code}"

    def is_home_team(self, team_id: int) -> bool:
        """Check if team ID is home team."""
        return team_id == self.home_team_id

    def is_away_team(self, team_id: int) -> bool:
        """Check if team ID is away team."""
        return team_id == self.away_team_id

    @classmethod
    def from_raw(cls, raw: dict) -> "MatchMetadata":
        """Parse match metadata from raw MatchData event."""
        # Parse players
        home_players = [
            Player(
                id=p["Id"],
                team_id=p["TeamId"],
                first_name=p.get("FirstName", ""),
                last_name=p.get("LastName", ""),
                shirt_no=p.get("ShirtNo"),
                is_coach=p.get("IsCoach", False),
                is_captain=p.get("IsCaptain", False),
                is_starter=p.get("IsStarter", False),
                shoots=p.get("Shoots", ""),
                birthday=p.get("Birthday"),
                picture_file_id=p.get("PictureFileId"),
                weight=p.get("Weight"),
                height=p.get("Height"),
            )
            for p in raw.get("HomePlayers", [])
        ]

        away_players = [
            Player(
                id=p["Id"],
                team_id=p["TeamId"],
                first_name=p.get("FirstName", ""),
                last_name=p.get("LastName", ""),
                shirt_no=p.get("ShirtNo"),
                is_coach=p.get("IsCoach", False),
                is_captain=p.get("IsCaptain", False),
                is_starter=p.get("IsStarter", False),
                shoots=p.get("Shoots", ""),
                birthday=p.get("Birthday"),
                picture_file_id=p.get("PictureFileId"),
                weight=p.get("Weight"),
                height=p.get("Height"),
            )
            for p in raw.get("AwayPlayers", [])
        ]

        home_coaches = [
            Player(
                id=p["Id"],
                team_id=p["TeamId"],
                first_name=p.get("FirstName", ""),
                last_name=p.get("LastName", ""),
                shirt_no=p.get("ShirtNo"),
                is_coach=True,
                is_captain=p.get("IsCaptain", False),
                is_starter=p.get("IsStarter", False),
                shoots=p.get("Shoots", ""),
                birthday=p.get("Birthday"),
                picture_file_id=p.get("PictureFileId"),
                weight=p.get("Weight"),
                height=p.get("Height"),
            )
            for p in raw.get("HomeCoaches", [])
        ]

        away_coaches = [
            Player(
                id=p["Id"],
                team_id=p["TeamId"],
                first_name=p.get("FirstName", ""),
                last_name=p.get("LastName", ""),
                shirt_no=p.get("ShirtNo"),
                is_coach=True,
                is_captain=p.get("IsCaptain", False),
                is_starter=p.get("IsStarter", False),
                shoots=p.get("Shoots", ""),
                birthday=p.get("Birthday"),
                picture_file_id=p.get("PictureFileId"),
                weight=p.get("Weight"),
                height=p.get("Height"),
            )
            for p in raw.get("AwayCoaches", [])
        ]

        # Parse periods
        periods = [
            Period(
                id=p["PartialResultTypeId"],
                name=p["Name"],
                duration=p["Duration"],
                is_active=p["IsActive"],
                is_overtime=p.get("IsOvertimeType", False),
                is_shootout=p.get("IsShootoutType", False),
                sort_order=p["SortOrder"],
                time_ascending=p.get("TimeAscending", True),
            )
            for p in raw.get("Periods", [])
        ]

        # Parse referees
        referees = [
            Referee(
                id=r["Id"],
                name=r["Name"],
                type=r.get("Type", ""),
            )
            for r in raw.get("Referees", [])
        ]

        return cls(
            match_id=raw["MatchId"],
            tournament_id=raw.get("TournamentId", 0),
            tournament_name=raw.get("TournamentName", ""),
            home_team_id=raw.get("HomeTeamId", 0),
            away_team_id=raw.get("AwayTeamId", 0),
            home_team_name=raw.get("HomeTeam", ""),
            away_team_name=raw.get("AwayTeam", ""),
            activity_area=raw.get("ActivityArea", ""),
            activity_area_id=raw.get("ActivityAreaId", 0),
            venue_id=raw.get("VenueId", 0),
            venue_no=raw.get("VenueNo", ""),
            match_date=raw.get("MatchDate", ""),
            match_start_time=raw.get("MatchStartTime"),
            home_players=home_players,
            away_players=away_players,
            home_coaches=home_coaches,
            away_coaches=away_coaches,
            periods=periods,
            referees=referees,
            attendance=raw.get("Attendance", -1),
            live_arena=raw.get("LiveArena", False),
            live_arena_status=raw.get("LiveArenaStatus", 0),
            registration_mode=raw.get("RegistrationMode", 0),
        )

    def to_summary(self) -> str:
        """Generate a text summary of the match."""
        lines = [
            f"Match ID: {self.match_id}",
            f"Tournament: {self.tournament_name}",
            f"",
            f"Home: {self.home_team_name}",
            f"Away: {self.away_team_name}",
            f"",
            f"Venue: {self.activity_area}",
            f"Date: {self.match_date}",
            f"",
            f"Home Players: {len(self.home_players)}",
            f"Away Players: {len(self.away_players)}",
            f"Periods: {len(self.periods)}",
            f"Referees: {len(self.referees)}",
        ]
        return "\n".join(lines)
