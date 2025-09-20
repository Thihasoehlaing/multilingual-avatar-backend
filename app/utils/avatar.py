def avatar_for_gender(gender: str | None) -> dict:
    male = {
        "model": "/avatars/male.glb",
        "morphMap": {"AA":0,"O":1,"E":2,"FV":3,"L":4,"MBP":5,"WQ":6,"rest":7}
    }
    female = {
        "model": "/avatars/female.glb",
        "morphMap": {"AA":0,"O":1,"E":2,"FV":3,"L":4,"MBP":5,"WQ":6,"rest":7}
    }
    return male if gender == "male" else female
