# Write your solution here
def run(program):
    variables = {chr(i): 0 for i in range(ord("A"), ord("Z") + 1)}

    labels = {}
    for i, line in enumerate(program):
        if line.endswith(":"):
            labels[line[:-1]] = i

    def get_value(token):
        if token in variables:
            return variables[token]
        return int(token)

    output = []
    counter = 0

    while counter < len(program):
        parts = program[counter].split()
        cmd = parts[0]

        if cmd == "END":
            break
        elif cmd.endswith(":"):
            counter += 1
        elif cmd == "PRINT":
            output.append(get_value(parts[1]))
            counter += 1
        elif cmd == "MOV":
            variables[parts[1]] = get_value(parts[2])
            counter += 1
        elif cmd == "ADD":
            variables[parts[1]] += get_value(parts[2])
            counter += 1
        elif cmd == "SUB":
            variables[parts[1]] -= get_value(parts[2])
            counter += 1
        elif cmd == "MUL":
            variables[parts[1]] *= get_value(parts[2])
            counter += 1
        elif cmd == "JUMP":
            counter = labels[parts[1]]
        elif cmd == "IF":
            val1 = get_value(parts[1])
            op = parts[2]
            val2 = get_value(parts[3])
            loc = parts[5]

            condition = False
            if op == "==":
                condition = val1 == val2
            if op == "!=":
                condition = val1 != val2
            if op == "<":
                condition = val1 < val2
            if op == "<=":
                condition = val1 <= val2
            if op == ">":
                condition = val1 > val2
            if op == ">=":
                condition = val1 >= val2

            if condition:
                counter = labels[loc]
            else:
                counter += 1
        else:
            counter += 1
    return output