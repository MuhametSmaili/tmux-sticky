# Input: legacy or tmux JSON V2 layout. Output: legacy geometry, no checksum.
# With pane unset, normalize only; otherwise predict removal of that pane.
# Unsupported geometry fails closed; native metadata is not reconstructed.
# This is a geometry adapter, not a general JSON or native-metadata validator.
function space() { while (substr(text, pos, 1) ~ /^[ \t\r\n]$/) pos++ }
function number(    part) {
    space()
    if (!match(substr(text, pos), /^[0-9]+/)) exit 1
    part = substr(text, pos, RLENGTH)
    pos += RLENGTH
    return part + 0
}
function take(value) {
    space()
    if (substr(text, pos++, 1) != value) exit 1
}
function cell(depth,    node, mark, closing, nextnode) {
    if (depth > 128) exit 1
    node = ++nodes
    width[node] = number(); take("x")
    height[node] = number(); take(",")
    xpos[node] = number(); take(",")
    ypos[node] = number()
    mark = substr(text, pos++, 1)
    if (mark == ",") {
        kind[node] = "pane"
        id[node] = number()
        return node
    }
    if (mark != "{" && mark != "[") exit 1
    kind[node] = mark
    closing = mark == "{" ? "}" : "]"
    while (1) {
        nextnode = cell(depth + 1)
        child[node, ++count[node]] = nextnode
        mark = substr(text, pos++, 1)
        if (mark == closing) break
        if (mark != ",") exit 1
    }
    return node
}
function json_string(    end, value) {
    take("\"")
    end = index(substr(text, pos), "\"")
    if (!end) exit 1
    value = substr(text, pos, end - 1)
    if (index(value, "\\")) exit 1
    pos += end
    return value
}
function json_cell(depth,    node, key, value, mark) {
    if (depth > 128) exit 1
    node = ++nodes
    take("{")
    while (1) {
        key = json_string()
        if (seen[node, key]++) exit 1
        take(":")
        if (key == "t") {
            value = json_string()
            if (value == "p") kind[node] = "pane"
            else if (value == "h") kind[node] = "{"
            else if (value == "v") kind[node] = "["
            else exit 1
        } else if (key == "w") width[node] = number()
        else if (key == "h") height[node] = number()
        else if (key == "x") xpos[node] = number()
        else if (key == "y") ypos[node] = number()
        else if (key == "I") {
            value = json_string()
            if (value !~ /^%[0-9]+$/) exit 1
            id[node] = substr(value, 2) + 0
        } else if (key == "c") {
            take("[")
            while (1) {
                child[node, ++count[node]] = json_cell(depth + 1)
                space()
                mark = substr(text, pos++, 1)
                if (mark == "]") break
                if (mark != ",") exit 1
            }
        } else if (key == "i" || key == "l") value = number()
        else if (key == "a") {
            space()
            if (substr(text, pos, 4) == "true") pos += 4
            else if (substr(text, pos, 5) == "false") pos += 5
            else exit 1
        } else exit 1
        space()
        mark = substr(text, pos++, 1)
        if (mark == "}") break
        if (mark != ",") exit 1
    }
    if (!seen[node, "t"] || !seen[node, "w"] || !seen[node, "h"] || !seen[node, "x"] || !seen[node, "y"]) exit 1
    if (width[node] < 1 || height[node] < 1) exit 1
    if (kind[node] == "pane") {
        if (!seen[node, "I"] || seen[node, "c"]) exit 1
    } else if (count[node] < 2 || seen[node, "I"]) exit 1
    return node
}
function validate(node,    i, nextnode, cursor) {
    if (width[node] < 1 || height[node] < 1) exit 1
    if (kind[node] == "pane") {
        if (pane_seen[id[node]]++) exit 1
        return
    }
    if (count[node] < 2) exit 1
    cursor = kind[node] == "{" ? xpos[node] : ypos[node]
    for (i = 1; i <= count[node]; i++) {
        nextnode = child[node, i]
        if (kind[node] == "{") {
            if (xpos[nextnode] != cursor || ypos[nextnode] != ypos[node] || height[nextnode] != height[node]) exit 1
            cursor += width[nextnode] + 1
        } else {
            if (ypos[nextnode] != cursor || xpos[nextnode] != xpos[node] || width[nextnode] != width[node]) exit 1
            cursor += height[nextnode] + 1
        }
        validate(nextnode)
    }
    if (kind[node] == "{") {
        if (cursor - 1 != xpos[node] + width[node]) exit 1
    } else if (cursor - 1 != ypos[node] + height[node]) exit 1
}
function grow(node, amount,    i) {
    width[node] += amount
    if (kind[node] == "pane") return
    if (kind[node] == "[") {
        for (i = 1; i <= count[node]; i++) grow(child[node, i], amount)
    } else {
        # Native tmux distributes one column per child in order, recursively.
        for (i = 0; i < amount; i++) grow(child[node, (i % count[node]) + 1], 1)
    }
}
function offsets(node, x, y,    i, nextnode) {
    xpos[node] = x; ypos[node] = y
    for (i = 1; i <= count[node]; i++) {
        nextnode = child[node, i]
        offsets(nextnode, x, y)
        if (kind[node] == "{") x += width[nextnode] + 1
        else y += height[nextnode] + 1
    }
}
function dump(node,    result, i) {
    result = sprintf("%dx%d,%d,%d", width[node], height[node], xpos[node], ypos[node])
    if (kind[node] == "pane") return result "," id[node]
    result = result kind[node]
    for (i = 1; i <= count[node]; i++)
        result = result (i == 1 ? "" : ",") dump(child[node, i])
    return result (kind[node] == "{" ? "}" : "]")
}
{
    text = $0
    sub(/^[[:xdigit:]]+,/, "", text)
    pos = 1
    space()
    if (substr(text, pos, 1) == "{") {
        take("{")
        if (json_string() != "V") exit 1
        take(":")
        if (number() != 2) exit 1
        take(",")
        if (json_string() != "L") exit 1
        take(":")
        root = json_cell(0)
        take("}")
    } else root = cell(0)
    space()
    if (pos != length(text) + 1 || xpos[root] != 0 || ypos[root] != 0) exit 1
    validate(root)
    if (pane == "") { print dump(root); next }
    if (kind[root] != "{" || count[root] < 2) exit 1
    edge = child[root, 1]
    last = count[root]
    if (kind[edge] == "pane" && id[edge] == pane) {
        neighbor = child[root, 2]
        for (i = 1; i < last; i++) child[root, i] = child[root, i + 1]
    } else {
        edge = child[root, last]
        if (kind[edge] != "pane" || id[edge] != pane) exit 1
        neighbor = child[root, last - 1]
    }
    if (height[edge] != height[root] || ypos[edge] != ypos[root]) exit 1
    grow(neighbor, width[edge] + 1)
    count[root]--
    if (count[root] == 1) root = child[root, 1]
    offsets(root, 0, 0)
    print dump(root)
}
