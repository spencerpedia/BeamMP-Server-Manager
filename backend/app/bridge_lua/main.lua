-- BeamMP Server Manager bridge plugin.
-- Installed and overwritten by the manager on every server start; edits here will be lost.
-- Reports player and chat events as "[BMSM]{json}" lines on stdout and enforces the manager's ban list.

local BANS_FILE = ".bmsm/bans.json"

local function emit(kind, data)
    data = data or {}
    data.t = kind
    print("[BMSM]" .. Util.JsonEncode(data))
end

local function readBans()
    local f = io.open(BANS_FILE, "r")
    if not f then return {} end
    local raw = f:read("*a")
    f:close()
    local ok, decoded = pcall(Util.JsonDecode, raw)
    if ok and type(decoded) == "table" then return decoded end
    return {}
end

local function findBan(name, ids)
    local lname = string.lower(name or "")
    ids = ids or {}
    for _, b in pairs(readBans()) do
        if (b.name or "") ~= "" and string.lower(b.name) == lname then return b end
        if (b.beammp or "") ~= "" and tostring(ids.beammp or "") == b.beammp then return b end
        if (b.ip or "") ~= "" and tostring(ids.ip or "") == b.ip then return b end
    end
    return nil
end

local function playerInfo(id, name)
    local ids = MP.GetPlayerIdentifiers(id) or {}
    local cars = 0
    local vehicles = MP.GetPlayerVehicles(id)
    if vehicles then
        for _ in pairs(vehicles) do cars = cars + 1 end
    end
    return {
        id = id,
        name = name or MP.GetPlayerName(id),
        beammp = ids.beammp and tostring(ids.beammp) or "",
        ip = ids.ip or "",
        guest = MP.IsPlayerGuest(id) or false,
        cars = cars,
    }
end

function bmsmOnAuth(name, role, isGuest, identifiers)
    local ban = findBan(name, identifiers)
    if ban then
        emit("ban_reject", { name = name, reason = ban.reason or "" })
        local reason = "You are banned from this server"
        if (ban.reason or "") ~= "" then reason = reason .. ": " .. ban.reason end
        return reason
    end
end

function bmsmOnJoin(id)
    emit("join", playerInfo(id))
end

function bmsmOnDisconnect(id)
    emit("leave", { id = id, name = MP.GetPlayerName(id) })
end

function bmsmOnChat(id, name, message)
    emit("chat", { id = id, name = name, message = message })
end

function bmsmTick()
    local list = {}
    for id, name in pairs(MP.GetPlayers() or {}) do
        table.insert(list, playerInfo(id, name))
    end
    emit("players", { players = list })
end

-- Console commands from the manager: "bmsm kick <id> [reason]" and "bmsm enforcebans".
function bmsmOnConsole(input)
    local cmd, rest = string.match(input, "^bmsm%s+(%S+)%s*(.*)$")
    if not cmd then return nil end
    if cmd == "kick" then
        local id, reason = string.match(rest, "^(%d+)%s*(.*)$")
        if id then
            MP.DropPlayer(tonumber(id), reason ~= "" and reason or "Kicked")
            return "kicked player " .. id
        end
        return "usage: bmsm kick <id> [reason]"
    elseif cmd == "enforcebans" then
        local dropped = 0
        for id, name in pairs(MP.GetPlayers() or {}) do
            local ban = findBan(name, MP.GetPlayerIdentifiers(id))
            if ban then
                MP.DropPlayer(id, "You are banned from this server")
                dropped = dropped + 1
            end
        end
        return "ban list enforced, dropped " .. dropped
    elseif cmd == "players" then
        bmsmTick()
        return ""
    end
    return "unknown bmsm command"
end

MP.RegisterEvent("onPlayerAuth", "bmsmOnAuth")
MP.RegisterEvent("onPlayerJoin", "bmsmOnJoin")
MP.RegisterEvent("onPlayerDisconnect", "bmsmOnDisconnect")
MP.RegisterEvent("onChatMessage", "bmsmOnChat")
MP.RegisterEvent("onConsoleInput", "bmsmOnConsole")
MP.RegisterEvent("bmsmTick", "bmsmTick")
MP.CreateEventTimer("bmsmTick", 5000)
emit("ready", {})
