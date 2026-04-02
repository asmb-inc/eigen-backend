from supabase_client import supabase


def process_contest(contest_id):
    resp = supabase.rpc("process_contest", {
        "p_contest_id": contest_id
    }).execute()

    if resp.data is None:
        print("❌ Failed to process contest")
        return

    data = resp.data

    print(f"\n📊 Contest {contest_id} Results:\n")

    for row in data:
        print(
            f"User {row['profile_id']} | "
            f"Rank {row['rank']} | "
            f"{row['old_rating']} → {row['new_rating']} "
            f"(Δ {row['delta']})"
        )

    print("\n✅ Done")


if __name__ == "__main__":
    contest_id = int(input("Enter contest id: "))
    process_contest(contest_id)