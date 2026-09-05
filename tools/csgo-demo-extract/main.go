package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	dem "github.com/markus-wa/demoinfocs-golang/v4/pkg/demoinfocs"
	common "github.com/markus-wa/demoinfocs-golang/v4/pkg/demoinfocs/common"
	events "github.com/markus-wa/demoinfocs-golang/v4/pkg/demoinfocs/events"
)

const extractorVersion = "csgo-extract-1"

type headerOut struct {
	HeaderName       string  `json:"headername"`
	MapName          string  `json:"map_name"`
	ServerName       string  `json:"server_name"`
	ClientName       string  `json:"client_name"`
	PlaybackTicks    int     `json:"playback_ticks"`
	PlaybackTime     float64 `json:"playback_time"`
	TickRate         float64 `json:"tick_rate"`
	Tickrate         float64 `json:"tickrate"`
	NetworkProtocol  int     `json:"network_protocol"`
	ExtractorVersion string  `json:"extractor_version"`
}

type playerInfo struct {
	Name     string `json:"name"`
	Steamid  string `json:"steamid"`
	UserID   int    `json:"user_id"`
	EntityID int    `json:"entity_id"`
	TeamNum  int    `json:"team_number"`
	Team     int    `json:"team_num"`
}

func main() {
	demoPath := flag.String("demo", "", "path to a CS:GO .dem file")
	outDir := flag.String("out", "", "output directory")
	sampleHz := flag.Float64("sample-hz", 32, "tick snapshot frequency")
	showVersion := flag.Bool("version", false, "print extractor version")
	flag.Parse()
	if *showVersion {
		fmt.Println(extractorVersion)
		return
	}
	if *demoPath == "" || *outDir == "" {
		fmt.Fprintln(os.Stderr, "usage: csgo-demo-extract --demo match.dem --out dump-dir")
		os.Exit(2)
	}
	if err := extract(*demoPath, *outDir, *sampleHz); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func extract(demoPath, outDir string, sampleHz float64) error {
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	f, err := os.Open(demoPath)
	if err != nil {
		return err
	}
	defer f.Close()

	parser := dem.NewParser(f)
	defer parser.Close()

	hdr, err := parser.ParseHeader()
	if err != nil {
		return fmt.Errorf("parse header: %w", err)
	}
	playbackTime := durationSeconds(hdr.PlaybackTime)
	tickRate := 64.0
	if playbackTime > 0.05 && hdr.PlaybackTicks > 0 {
		tickRate = float64(hdr.PlaybackTicks) / playbackTime
		if tickRate < 16 || tickRate > 256 {
			tickRate = 64
		}
	}
	header := headerOut{
		HeaderName:       "HL2DEMO",
		MapName:          hdr.MapName,
		ServerName:       hdr.ServerName,
		ClientName:       hdr.ClientName,
		PlaybackTicks:    int(hdr.PlaybackTicks),
		PlaybackTime:     playbackTime,
		TickRate:         tickRate,
		Tickrate:         tickRate,
		NetworkProtocol:  int(hdr.NetworkProtocol),
		ExtractorVersion: extractorVersion,
	}
	if err := writeJSON(filepath.Join(outDir, "header.json"), header); err != nil {
		return err
	}

	eventsPath := filepath.Join(outDir, "events.jsonl")
	ticksPath := filepath.Join(outDir, "ticks.jsonl")
	ef, err := os.Create(eventsPath)
	if err != nil {
		return err
	}
	defer ef.Close()
	tf, err := os.Create(ticksPath)
	if err != nil {
		return err
	}
	defer tf.Close()
	ew := bufio.NewWriterSize(ef, 1<<20)
	tw := bufio.NewWriterSize(tf, 1<<20)
	defer ew.Flush()
	defer tw.Flush()

	sampleEvery := int(tickRate / sampleHz)
	if sampleEvery < 1 {
		sampleEvery = 1
	}
	lastSample := -sampleEvery
	playersBySteam := map[string]playerInfo{}

	writeEvent := func(payload map[string]any) {
		line, _ := json.Marshal(payload)
		ew.Write(line)
		ew.WriteByte('\n')
	}
	snapshot := func(force bool) {
		gs := parser.GameState()
		tick := gs.IngameTick()
		if !force && tick-lastSample < sampleEvery {
			return
		}
		lastSample = tick
		players := make([]map[string]any, 0, 10)
		for _, p := range gs.Participants().Playing() {
			if p == nil {
				continue
			}
			row := playerRow(p, tick)
			players = append(players, row)
			sid := fmt.Sprintf("%d", p.SteamID64)
			if sid != "0" {
				playersBySteam[sid] = playerInfo{
					Name:     p.Name,
					Steamid:  sid,
					UserID:   p.UserID,
					EntityID: p.EntityID,
					TeamNum:  int(p.Team),
					Team:     int(p.Team),
				}
			}
		}
		line, _ := json.Marshal(map[string]any{"tick": tick, "players": players})
		tw.Write(line)
		tw.WriteByte('\n')
	}

	attachPlayer := func(prefix string, p *common.Player, out map[string]any) {
		if p == nil {
			return
		}
		pos := p.Position()
		out[prefix+"name"] = p.Name
		out[prefix+"steamid"] = fmt.Sprintf("%d", p.SteamID64)
		out[prefix+"user_id"] = p.UserID
		out[prefix+"team_num"] = int(p.Team)
		out[prefix+"X"] = pos.X
		out[prefix+"Y"] = pos.Y
		out[prefix+"Z"] = pos.Z
		out[prefix+"yaw"] = p.ViewDirectionX()
		out[prefix+"pitch"] = p.ViewDirectionY()
	}

	parser.RegisterEventHandler(func(e events.Kill) {
		tick := parser.GameState().IngameTick()
		row := map[string]any{
			"event_name":    "player_death",
			"tick":          tick,
			"weapon":        weaponKey(e.Weapon),
			"headshot":      boolToInt(e.IsHeadshot),
			"penetrated":    e.PenetratedObjects,
			"thrusmoke":     boolToInt(e.ThroughSmoke),
			"noscope":       boolToInt(e.NoScope),
			"attackerblind": boolToInt(e.AttackerBlind),
			"assistedflash": boolToInt(e.AssistedFlash),
		}
		attachPlayer("user_", e.Victim, row)
		attachPlayer("attacker_", e.Killer, row)
		attachPlayer("assister_", e.Assister, row)
		writeEvent(row)
		snapshot(true)
	})
	parser.RegisterEventHandler(func(e events.PlayerHurt) {
		tick := parser.GameState().IngameTick()
		row := map[string]any{
			"event_name": "player_hurt",
			"tick":       tick,
			"weapon":     weaponKey(e.Weapon),
			"dmg_health": e.HealthDamage,
			"dmg_armor":  e.ArmorDamage,
			"hitgroup":   int(e.HitGroup),
			"health":     e.Health,
			"armor":      e.Armor,
		}
		attachPlayer("user_", e.Player, row)
		attachPlayer("attacker_", e.Attacker, row)
		writeEvent(row)
	})
	parser.RegisterEventHandler(func(e events.WeaponFire) {
		tick := parser.GameState().IngameTick()
		row := map[string]any{
			"event_name": "weapon_fire",
			"tick":       tick,
			"weapon":     weaponKey(e.Weapon),
		}
		attachPlayer("user_", e.Shooter, row)
		writeEvent(row)
	})
	parser.RegisterEventHandler(func(e events.PlayerFlashed) {
		tick := parser.GameState().IngameTick()
		row := map[string]any{
			"event_name":     "player_blind",
			"tick":           tick,
			"flash_duration": 0.0,
			"blind_duration": 0.0,
		}
		if e.Player != nil {
			row["flash_duration"] = e.Player.FlashDuration
			row["blind_duration"] = e.Player.FlashDuration
		}
		attachPlayer("user_", e.Player, row)
		attachPlayer("attacker_", e.Attacker, row)
		writeEvent(row)
	})
	parser.RegisterEventHandler(func(e events.BombPlanted) {
		tick := parser.GameState().IngameTick()
		row := map[string]any{"event_name": "bomb_planted", "tick": tick, "site": siteName(e.Site)}
		attachPlayer("user_", e.Player, row)
		writeEvent(row)
		snapshot(true)
	})
	parser.RegisterEventHandler(func(e events.BombDefused) {
		tick := parser.GameState().IngameTick()
		row := map[string]any{"event_name": "bomb_defused", "tick": tick, "site": siteName(e.Site)}
		attachPlayer("user_", e.Player, row)
		attachPlayer("defuser_", e.Player, row)
		writeEvent(row)
		snapshot(true)
	})
	parser.RegisterEventHandler(func(e events.BombExplode) {
		tick := parser.GameState().IngameTick()
		row := map[string]any{"event_name": "bomb_exploded", "tick": tick, "site": siteName(e.Site)}
		writeEvent(row)
		snapshot(true)
	})
	parser.RegisterEventHandler(func(e events.BombDefuseStart) {
		tick := parser.GameState().IngameTick()
		row := map[string]any{"event_name": "bomb_begindefuse", "tick": tick, "haskit": boolToInt(e.HasKit)}
		attachPlayer("user_", e.Player, row)
		writeEvent(row)
	})
	parser.RegisterEventHandler(func(e events.BombDropped) {
		tick := parser.GameState().IngameTick()
		row := map[string]any{"event_name": "bomb_dropped", "tick": tick}
		attachPlayer("user_", e.Player, row)
		writeEvent(row)
	})
	parser.RegisterEventHandler(func(e events.BombPickup) {
		tick := parser.GameState().IngameTick()
		row := map[string]any{"event_name": "bomb_pickup", "tick": tick}
		attachPlayer("user_", e.Player, row)
		writeEvent(row)
	})
	parser.RegisterEventHandler(func(e events.ItemPickup) {
		tick := parser.GameState().IngameTick()
		row := map[string]any{"event_name": "item_pickup", "tick": tick, "weapon": weaponKey(e.Weapon)}
		attachPlayer("user_", e.Player, row)
		writeEvent(row)
	})
	parser.RegisterEventHandler(func(e events.ItemEquip) {
		tick := parser.GameState().IngameTick()
		row := map[string]any{"event_name": "item_equip", "tick": tick, "weapon": weaponKey(e.Weapon)}
		attachPlayer("user_", e.Player, row)
		writeEvent(row)
	})
	parser.RegisterEventHandler(func(e events.GrenadeProjectileThrow) {
		tick := parser.GameState().IngameTick()
		wep := ""
		if e.Projectile != nil {
			wep = weaponKey(e.Projectile.WeaponInstance)
		}
		row := map[string]any{"event_name": "grenade_thrown", "tick": tick, "weapon": wep}
		if e.Projectile != nil {
			attachPlayer("user_", e.Projectile.Thrower, row)
		}
		writeEvent(row)
	})
	parser.RegisterEventHandler(func(e events.HeExplode) {
		writeNadeEvent(parser, writeEvent, snapshot, "hegrenade_detonate", e.Position.X, e.Position.Y, e.Position.Z, e.Thrower)
	})
	parser.RegisterEventHandler(func(e events.FlashExplode) {
		writeNadeEvent(parser, writeEvent, snapshot, "flashbang_detonate", e.Position.X, e.Position.Y, e.Position.Z, e.Thrower)
	})
	parser.RegisterEventHandler(func(e events.SmokeStart) {
		writeNadeEvent(parser, writeEvent, snapshot, "smokegrenade_detonate", e.Position.X, e.Position.Y, e.Position.Z, e.Thrower)
	})
	parser.RegisterEventHandler(func(e events.DecoyStart) {
		writeNadeEvent(parser, writeEvent, snapshot, "decoy_started", e.Position.X, e.Position.Y, e.Position.Z, e.Thrower)
	})
	parser.RegisterEventHandler(func(e events.InfernoStart) {
		if e.Inferno == nil {
			return
		}
		pos := e.Inferno.Entity.Position()
		thrower := e.Inferno.Thrower()
		writeNadeEvent(parser, writeEvent, snapshot, "inferno_startburn", pos.X, pos.Y, pos.Z, thrower)
		writeNadeEvent(parser, writeEvent, snapshot, "molotov_detonate", pos.X, pos.Y, pos.Z, thrower)
	})
	parser.RegisterEventHandler(func(e events.RoundStart) {
		tick := parser.GameState().IngameTick()
		writeEvent(map[string]any{"event_name": "round_start", "tick": tick})
		snapshot(true)
	})
	parser.RegisterEventHandler(func(e events.RoundFreezetimeEnd) {
		tick := parser.GameState().IngameTick()
		writeEvent(map[string]any{"event_name": "round_freeze_end", "tick": tick})
		snapshot(true)
	})
	parser.RegisterEventHandler(func(e events.RoundEnd) {
		tick := parser.GameState().IngameTick()
		writeEvent(map[string]any{
			"event_name":          "round_end",
			"tick":                tick,
			"winner":              int(e.Winner),
			"reason":              int(e.Reason),
			"total_rounds_played": parser.GameState().TotalRoundsPlayed(),
		})
		snapshot(true)
	})
	parser.RegisterEventHandler(func(e events.MatchStart) {
		tick := parser.GameState().IngameTick()
		writeEvent(map[string]any{"event_name": "round_announce_match_start", "tick": tick})
		snapshot(true)
	})
	parser.RegisterEventHandler(func(events.FrameDone) {
		snapshot(false)
	})

	if err := parser.ParseToEnd(); err != nil {
		msg := strings.ToLower(err.Error())
		if !strings.Contains(msg, "unexpected") && !strings.Contains(msg, "eof") && !strings.Contains(msg, "ended") {
			return fmt.Errorf("parse demo: %w", err)
		}
	}
	snapshot(true)

	list := make([]playerInfo, 0, len(playersBySteam))
	for _, p := range playersBySteam {
		list = append(list, p)
	}
	return writeJSON(filepath.Join(outDir, "players.json"), list)
}

func durationSeconds(value any) float64 {
	switch t := value.(type) {
	case float64:
		return t
	case float32:
		return float64(t)
	case interface{ Seconds() float64 }:
		return t.Seconds()
	default:
		return 0
	}
}

func writeNadeEvent(
	parser dem.Parser,
	writeEvent func(map[string]any),
	snapshot func(bool),
	name string,
	x, y, z float64,
	thrower *common.Player,
) {
	tick := parser.GameState().IngameTick()
	row := map[string]any{
		"event_name": name,
		"tick":       tick,
		"x":          x,
		"y":          y,
		"z":          z,
		"user_X":     x,
		"user_Y":     y,
		"user_Z":     z,
	}
	if thrower != nil {
		row["user_name"] = thrower.Name
		row["user_steamid"] = fmt.Sprintf("%d", thrower.SteamID64)
		row["user_team_num"] = int(thrower.Team)
	}
	writeEvent(row)
	snapshot(true)
}

func playerRow(p *common.Player, tick int) map[string]any {
	pos := p.Position()
	inv := make([]string, 0, 8)
	hasC4 := false
	hasDefuser := p.HasDefuseKit()
	for _, w := range p.Weapons() {
		if w == nil {
			continue
		}
		key := weaponKey(w)
		if key == "" {
			continue
		}
		inv = append(inv, key)
		if key == "c4" {
			hasC4 = true
		}
	}
	active := ""
	if w := p.ActiveWeapon(); w != nil {
		active = weaponKey(w)
	}
	return map[string]any{
		"tick":                tick,
		"name":                p.Name,
		"steamid":             fmt.Sprintf("%d", p.SteamID64),
		"user_id":             p.UserID,
		"entity_id":           p.EntityID,
		"team_num":            int(p.Team),
		"X":                   pos.X,
		"Y":                   pos.Y,
		"Z":                   pos.Z,
		"yaw":                 p.ViewDirectionX(),
		"pitch":               p.ViewDirectionY(),
		"is_alive":            p.IsAlive(),
		"health":              p.Health(),
		"armor":               p.Armor(),
		"has_helmet":          p.HasHelmet(),
		"balance":             p.Money(),
		"current_equip_value": p.EquipmentValueCurrent(),
		"inventory":           inv,
		"active_weapon":       active,
		"active_weapon_name":  active,
		"has_defuser":         hasDefuser,
		"has_c4":              hasC4,
		"flash_duration":      p.FlashDuration,
		"last_place_name":     "",
	}
}

func weaponKey(eq *common.Equipment) string {
	if eq == nil {
		return ""
	}
	s := strings.ToLower(eq.String())
	s = strings.TrimPrefix(s, "weapon_")
	compact := strings.NewReplacer(" ", "", "-", "", "_", "").Replace(s)
	if mapped, ok := compactWeapons[compact]; ok {
		return mapped
	}
	return strings.ReplaceAll(strings.ReplaceAll(s, " ", "_"), "-", "_")
}

var compactWeapons = map[string]string{
	"ak47": "ak47", "m4a4": "m4a1", "m4a1s": "m4a1_silencer", "m4a1silencer": "m4a1_silencer",
	"awp": "awp", "ssg08": "ssg08", "scout": "ssg08", "aug": "aug", "sg553": "sg556", "sg556": "sg556",
	"famas": "famas", "galil": "galilar", "galilar": "galilar", "galilarma": "galilar",
	"g3sg1": "g3sg1", "scar20": "scar20",
	"mp9": "mp9", "mp7": "mp7", "mp5sd": "mp5sd", "mac10": "mac10", "ump45": "ump45",
	"p90": "p90", "bizon": "bizon", "ppbizon": "bizon",
	"nova": "nova", "xm1014": "xm1014", "mag7": "mag7", "sawedoff": "sawedoff",
	"m249": "m249", "negev": "negev",
	"glock": "glock", "glock18": "glock", "usp": "usp_silencer", "usps": "usp_silencer",
	"uspsilencer": "usp_silencer", "p2000": "hkp2000", "hkp2000": "hkp2000",
	"p250": "p250", "fiveseven": "fiveseven", "tec9": "tec9", "cz75": "cz75a", "cz75auto": "cz75a",
	"deagle": "deagle", "deserteagle": "deagle", "r8revolver": "revolver", "revolver": "revolver",
	"dualberettas": "elite", "elite": "elite",
	"knife": "knife", "zeus": "taser", "zeusx27": "taser", "taser": "taser",
	"hegrenade": "hegrenade", "flashbang": "flashbang", "smokegrenade": "smokegrenade",
	"molotov": "molotov", "incgrenade": "incgrenade", "incendiarygrenade": "incgrenade",
	"decoy": "decoy", "c4": "c4", "defusekit": "defuse_kit",
}

func siteName(site events.Bombsite) string {
	switch site {
	case events.BombsiteA:
		return "A"
	case events.BombsiteB:
		return "B"
	default:
		return ""
	}
}

func boolToInt(v bool) int {
	if v {
		return 1
	}
	return 0
}

func writeJSON(path string, value any) error {
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o644)
}
