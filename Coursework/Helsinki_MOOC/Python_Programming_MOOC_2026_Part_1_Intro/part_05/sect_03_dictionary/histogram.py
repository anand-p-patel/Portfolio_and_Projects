# Write your solution here

def histogram(my_string):
    times_shown = {}
    for i in my_string :
        if i not in times_shown:
            times_shown[i] = 0
        times_shown[i] += 1

    for key, value in times_shown.items():
        print(f"{key} {value*"*"}")

if __name__ == "__main__":
    histogram("statistically")