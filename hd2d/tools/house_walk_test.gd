extends SceneTree
## 房子模式的走路檢查（不需要顯示卡）：從巷子走進大門、上到二樓、再上到閣樓、撞一下鎖著的車庫門。
## 只檢查「走得到、樓層有換、程式不出錯」，手感看不出來。用法（在專案根目錄）：
##   Godot_v4.7.2-stable_win64_console.exe --headless --path hd2d --script res://tools/house_walk_test.gd
## 最後一行印 WALK TEST OK 才算通過。

var house: Node3D
var failed := false


func _initialize() -> void:
	house = load("res://house.gd").new()
	root.add_child(house)
	_run.call_deferred()


func _walk(dx: float, dz: float, dist: float) -> void:
	var n := int(dist / 0.05)
	for i in n:
		house._step(Vector2(dx, dz), 0.05)


func _check(label: String, ok: bool) -> void:
	print("%s  %s  pos=(%.2f, %.2f) floor=%d stair=%d" % ["ok  " if ok else "FAIL", label, house.pos.x, house.pos.z, house.floor_i, house.on_stair])
	if not ok:
		failed = true


func _run() -> void:
	await process_frame
	_check("開場在巷子", house._room_at().is_empty())
	_walk(0, -1, 3.5)
	_check("走進大門到客廳", house._room_at().get("id", "") == "living")
	_walk(1, 0, 0.9)
	_walk(0, -1, 5.0)
	_walk(1, 0, 3.0)
	_check("踏上第一段樓梯", house.on_stair == 0)
	_walk(1, 0, 4.0)
	_check("上到二樓", house.floor_i == 1 and house.on_stair == -1 and house._room_at().get("id", "") == "hall")
	_walk(0, 1, 1.3)
	_walk(-1, 0, 2.0)
	_check("踏上第二段樓梯", house.on_stair == 1)
	_walk(-1, 0, 5.0)
	_check("上到閣樓", house.floor_i == 2 and house.on_stair == -1 and house._room_at().get("id", "") == "attic")
	_walk(1, 0, 6.0)
	_check("從閣樓走回二樓", house.floor_i == 1 and house.on_stair == -1)
	# 二樓：走進主臥再進浴室
	_walk(0, 1, 5.0)
	_walk(0, -1, 2.0)
	house.pos = Vector3(0.0, 0, 0.6)
	_walk(1, 0, 8.5)
	_check("穿過兩扇門到浴室", house._room_at().get("id", "") == "bath")
	# 一樓：廚房到車庫的門是鎖的
	house.floor_i = 0
	house.pos = Vector3(5.5, 0, 0.6)
	_walk(1, 0, 3.0)
	_check("車庫的門鎖著走不過去", house._room_at().get("id", "") == "kitchen" and house.msg.visible)
	print("WALK TEST FAILED" if failed else "WALK TEST OK")
	quit(1 if failed else 0)
