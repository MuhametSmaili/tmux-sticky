# Predict native removal of an unchanged, full-height edge sidebar.
# Input/output: legacy tmux layout, with the output checksum omitted.
# Unsupported or malformed layouts fail closed: never guess at user geometry.
function number(    part) {
    if (!match(substr(text, pos), /^[0-9]+/)) exit 1
    part = substr(text, pos, RLENGTH)
    pos += RLENGTH
    return part + 0
}
function take(value) {
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
    root = cell(0)
    if (pos != length(text) + 1 || kind[root] != "{" || count[root] < 2) exit 1
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
