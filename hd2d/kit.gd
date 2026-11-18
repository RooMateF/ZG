extends RefCounted
## 共用的小工具：場景貼圖、方塊家具、立牌、像素小人、環境、輸入、截圖。
## main.gd（測試房間）和 house.gd（房子）都用這一份，用法：const Kit := preload("res://kit.gd")
## 全部是 static，不存任何狀態。

const HERO_UNITS := 1.5                   # 178 公分的許晏在場景裡多高。其他人照身高比例縮放
const HERO_CM := 178.0
const SHEET_PIXEL := HERO_UNITS / 56.0    # 小人一個像素多大（小人從頭到腳 56 像素）。場景貼圖和家具用同一個密度


# ------------------------------------------------------------ 貼圖和材質
static func pixel_tex(size: int, base: Color, vary: float, grid: int = 0) -> ImageTexture:
	# 程式產生的暫代貼圖：底色加一點雜訊，grid > 0 時畫格線
	var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
	var rng := RandomNumberGenerator.new()
	rng.seed = hash(base.to_html()) + size
	for y in size:
		for x in size:
			var c := base
			var v := rng.randf_range(-vary, vary)
			c = Color(clampf(c.r + v, 0, 1), clampf(c.g + v, 0, 1), clampf(c.b + v, 0, 1))
			if grid > 0 and (x % grid == 0 or y % grid == 0):
				c = c.darkened(0.35)
			img.set_pixel(x, y, c)
	return ImageTexture.create_from_image(img)


static func tile_mat(file: String, fallback: Color = Color(0.5, 0.5, 0.5), grid: int = 0) -> StandardMaterial3D:
	# 場景貼圖 art/tiles/<file>.png。用世界座標三向投影，每個面的像素密度都和小人一樣。
	# 圖還沒交的時候，用 fallback 顏色產生一張暫代的，圖交了不用改程式。
	var m := StandardMaterial3D.new()
	var path := "res://art/tiles/%s.png" % file
	if ResourceLoader.exists(path):
		m.albedo_texture = load(path)
	else:
		m.albedo_texture = pixel_tex(32, fallback, 0.02, grid)
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	m.uv1_triplanar = true
	m.uv1_world_triplanar = true
	m.uv1_triplanar_sharpness = 150.0
	var per_unit := 1.0 / (SHEET_PIXEL * 32.0)             # 一張 32 像素的貼圖在世界裡多寬
	m.uv1_scale = Vector3(per_unit, per_unit, per_unit)
	m.roughness = 0.9
	return m


static func flat_mat(color: Color) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = 0.9
	return m


static func face_mat(file: String, mirror: bool = false) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_texture = load("res://art/furniture/%s.png" % file)
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	m.roughness = 0.9
	if mirror:
		m.uv1_scale = Vector3(-1, 1, 1)
	return m


static func quad(parent: Node3D, size: Vector2, pos: Vector3, rot: Vector3, mat: Material) -> void:
	var q := QuadMesh.new()
	q.size = size
	var mi := MeshInstance3D.new()
	mi.mesh = q
	mi.position = pos
	mi.rotation_degrees = rot
	mi.material_override = mat
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF      # 影子由看不見的方塊投
	parent.add_child(mi)


static func box(parent: Node3D, size: Vector3, pos: Vector3, mat: Material) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = size
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.position = pos
	mi.material_override = mat
	parent.add_child(mi)
	return mi


# ------------------------------------------------------------ 方塊家具和立牌
static func has_furniture_art(id: String) -> bool:
	return ResourceLoader.exists("res://art/furniture/%s_front.png" % id)


static func furniture_size(id: String, px: Vector3 = Vector3.ZERO) -> Vector3:
	# 寬、高、深（場景單位）。有圖就照貼圖的像素數，沒有圖就照 px（像素數）。
	if has_furniture_art(id):
		var f: Texture2D = load("res://art/furniture/%s_front.png" % id)
		var s: Texture2D = load("res://art/furniture/%s_side.png" % id)
		return Vector3(f.get_width(), f.get_height(), s.get_width()) * SHEET_PIXEL
	return px * SHEET_PIXEL


static func furniture(parent: Node3D, id: String, pos: Vector3, yaw: float = 0.0,
		px: Vector3 = Vector3.ZERO, color: Color = Color(0.6, 0.6, 0.62)) -> Vector3:
	# 方塊家具。art/furniture/<代號>_front、_top、_side 三張貼圖存在就用圖，大小照貼圖的像素數；
	# 不存在就放一個 px 大小的素色方塊佔位。pos 是底面中心。回傳寬、高、深。
	var size := furniture_size(id, px)
	var w := size.x
	var h := size.y
	var d := size.z
	var root := Node3D.new()
	root.position = pos + Vector3(0, h / 2, 0)
	root.rotation_degrees.y = yaw
	parent.add_child(root)
	var caster := MeshInstance3D.new()
	var bm := BoxMesh.new()
	caster.mesh = bm
	if has_furniture_art(id):
		var front := face_mat(id + "_front")
		var side := face_mat(id + "_side")
		var top: Material = side                                # 門這類薄板沒有頂面的圖，借側面的
		if ResourceLoader.exists("res://art/furniture/%s_top.png" % id):
			top = face_mat(id + "_top")
		var back: Material = front                              # 沒交背面就借正面的
		if ResourceLoader.exists("res://art/furniture/%s_back.png" % id):
			back = face_mat(id + "_back")
		quad(root, Vector2(w, h), Vector3(0, 0, d / 2), Vector3.ZERO, front)                      # 正面
		quad(root, Vector2(w, h), Vector3(0, 0, -d / 2), Vector3(0, 180, 0), back)                # 背面
		quad(root, Vector2(w, d), Vector3(0, h / 2, 0), Vector3(-90, 0, 0), top)                  # 頂面：圖的上緣朝後
		quad(root, Vector2(d, h), Vector3(w / 2, 0, 0), Vector3(0, 90, 0), side)                  # 右側：圖的左緣接正面
		quad(root, Vector2(d, h), Vector3(-w / 2, 0, 0), Vector3(0, -90, 0), face_mat(id + "_side", true))   # 左側：鏡射
		bm.size = size * 0.98
		caster.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY
	else:
		bm.size = size
		caster.material_override = flat_mat(color)
	root.add_child(caster)
	return size


static func footprint(pos: Vector3, size: Vector3, yaw: float = 0.0) -> Rect2:
	# 家具在地板上佔的範圍（x、z 平面）。轉了接近 90 度的，寬和深對調。
	var turned: bool = absf(fmod(absf(yaw), 180.0) - 90.0) < 45.0
	var ow: float = size.z if turned else size.x
	var od: float = size.x if turned else size.z
	return Rect2(pos.x - ow / 2, pos.z - od / 2, ow, od)


static func prop(parent: Node3D, file: String, pos: Vector3) -> Sprite3D:
	# 形狀不規則的小東西：透明底的單張圖，當成立牌放。四邊留白 2 像素。pos 是底部中心。
	var tex: Texture2D = load("res://art/furniture/%s.png" % file)
	var s := Sprite3D.new()
	s.texture = tex
	s.pixel_size = SHEET_PIXEL
	s.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	s.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	s.shaded = true
	s.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
	s.position = pos + Vector3(0, (tex.get_height() * 0.5 - 2.0) * SHEET_PIXEL, 0)
	parent.add_child(s)
	return s


# ------------------------------------------------------------ 像素小人
static func sheet_actor(parent: Node3D, id: String, pos: Vector3) -> Sprite3D:
	# 美術交的轉身圖匯入後的圖集（tools/import_turn.py）：4 欄走路格 × 3 列方向（朝下、朝右、朝上）
	# 腳底到圖片中心的距離存在 meta "foot"：要搬動小人時，y = 地面高度 + foot。
	var tex: Texture2D = load("res://art/sprites/%s.png" % id)
	var meta: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://art/sprites/%s.json" % id))
	var px: float = HERO_UNITS * (float(meta["cm"]) / HERO_CM) / float(meta["body_h"])   # 照身高縮放
	var s := Sprite3D.new()
	s.texture = tex
	s.hframes = int(meta["cols"])
	s.vframes = int(meta["rows"])
	s.frame = 0
	s.pixel_size = px
	s.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	s.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	s.shaded = true
	s.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
	var foot: float = (float(meta["frame_h"]) * 0.5 - float(meta["foot_pad"])) * px
	s.set_meta("foot", foot)
	s.position = pos + Vector3(0, foot, 0)                                                # 腳底貼地
	s.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	parent.add_child(s)
	return s


static func face_walk(s: Sprite3D, dir: Vector2, t: float) -> void:
	# 照移動方向換圖。dir.x 右為正，dir.y 朝鏡頭為正。t 是累計的走路時間；dir 為零時停在站姿。
	# 圖集第 0 列朝下（朝鏡頭走）、第 1 列朝側（往左時鏡像）、第 2 列朝上。
	if dir.length() < 0.01:
		s.frame_coords = Vector2i(0, s.frame_coords.y)
		return
	var row := 1 if absf(dir.x) > absf(dir.y) else (0 if dir.y > 0 else 2)
	s.flip_h = row == 1 and dir.x < 0
	s.frame_coords = Vector2i(int(t * 8.0) % 4, row)


# ------------------------------------------------------------ 環境和鏡頭
static func make_env() -> Environment:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.03, 0.04, 0.07)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.40, 0.42, 0.52)        # 藍得太重會把角色的顏色蓋掉
	env.ambient_light_energy = 0.6
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.glow_enabled = true
	env.glow_intensity = 0.9
	env.glow_bloom = 0.15
	env.glow_hdr_threshold = 0.85
	env.fog_enabled = true
	env.fog_light_color = Color(0.42, 0.36, 0.32)
	env.fog_density = 0.004                                  # 第一張截圖太霧，降到三分之一
	if RenderingServer.get_current_rendering_method() == "forward_plus":
		# PC 的 Forward+ 才有的效果。手機用的 Mobile 模式會跳過，畫面仍然成立（移植入口）。
		env.ssao_enabled = true
		env.ssao_intensity = 1.6
		env.volumetric_fog_enabled = true
		env.volumetric_fog_density = 0.003
		env.volumetric_fog_albedo = Color(0.9, 0.85, 0.8)
	return env


static func cam_attributes() -> CameraAttributesPractical:
	var attr := CameraAttributesPractical.new()   # 景深：前景和遠景都糊，中間清楚（移軸感）
	attr.dof_blur_far_enabled = true
	attr.dof_blur_far_distance = 10.5
	attr.dof_blur_far_transition = 3.5
	attr.dof_blur_near_enabled = true
	attr.dof_blur_near_distance = 5.0
	attr.dof_blur_near_transition = 2.0
	attr.dof_blur_amount = 0.11
	return attr


# ------------------------------------------------------------ 輸入和截圖
static func setup_input() -> void:
	# 動作名稱寫死、按鍵在這裡綁。之後要加別的裝置（觸控、別的手把）只改這裡。
	var binds := {
		"move_left": [[KEY_LEFT, KEY_A], JOY_AXIS_LEFT_X, -1.0],
		"move_right": [[KEY_RIGHT, KEY_D], JOY_AXIS_LEFT_X, 1.0],
		"move_up": [[KEY_UP, KEY_W], JOY_AXIS_LEFT_Y, -1.0],
		"move_down": [[KEY_DOWN, KEY_S], JOY_AXIS_LEFT_Y, 1.0],
	}
	for action in binds:
		if InputMap.has_action(action):
			continue
		InputMap.add_action(action, 0.25)
		for k in binds[action][0]:
			var ev := InputEventKey.new()
			ev.physical_keycode = k
			InputMap.action_add_event(action, ev)
		var jm := InputEventJoypadMotion.new()
		jm.axis = binds[action][1]
		jm.axis_value = binds[action][2]
		InputMap.action_add_event(action, jm)
	if not InputMap.has_action("run"):                       # 跑：Shift，或手把右肩鍵
		InputMap.add_action("run")
		var sh := InputEventKey.new()
		sh.physical_keycode = KEY_SHIFT
		InputMap.action_add_event("run", sh)
		var jb := InputEventJoypadButton.new()
		jb.button_index = JOY_BUTTON_RIGHT_SHOULDER
		InputMap.action_add_event("run", jb)


static func take_shot(node: Node, path: String, frame_no: int) -> void:
	# 等這一幀畫完再抓畫面，存檔後結束。給沒有顯示卡的機器用軟體繪圖看畫面用。
	await RenderingServer.frame_post_draw
	var img := node.get_viewport().get_texture().get_image()
	var err := img.save_png(path)
	print("SHOT %s err=%d size=%dx%d method=%s adapter=%s frames=%d" % [
		path, err, img.get_width(), img.get_height(),
		RenderingServer.get_current_rendering_method(), RenderingServer.get_video_adapter_name(), frame_no])
	node.get_tree().quit()
