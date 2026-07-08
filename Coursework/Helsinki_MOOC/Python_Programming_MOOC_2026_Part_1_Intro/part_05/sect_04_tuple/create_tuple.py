# Write your solution here
def create_tuple(x: int, y: int, z: int):
    smallest = min(x,y,z)
    largest = max(x, y,z)
    summed = x + y + z
    created_tuple = (smallest, largest, summed)


    return created_tuple

if __name__ == "__main__":
    print(create_tuple(5, 3, -1))