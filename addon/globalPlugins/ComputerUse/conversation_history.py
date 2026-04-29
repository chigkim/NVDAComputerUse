import copy


def latest_tool_results(messages):
	latest_tool_call_index = _latest_tool_call_index(messages)
	if latest_tool_call_index is None or latest_tool_call_index + 1 >= len(messages):
		return []

	results = []
	for message in messages[latest_tool_call_index + 1:]:
		if message.get("role") != "tool":
			continue
		content = message.get("content")
		if isinstance(content, str) and content:
			results.append(content)
	return results


def screenshot_text_for_messages(messages):
	results = latest_tool_results(messages)
	if not results:
		return "Latest screenshot."

	return "Previous tool result:\n%s\n\nLatest screenshot." % "\n".join(
		"- %s" % result for result in results
	)


def sanitize_messages(messages, trim_conversation=True):
	if trim_conversation:
		sanitized = _trim_tool_history(messages)
	else:
		sanitized = copy.deepcopy(messages)

	_keep_latest_image(sanitized, compact_screenshot_messages=trim_conversation)
	messages[:] = sanitized


def _trim_tool_history(messages):
	latest_tool_call_index = _latest_tool_call_index(messages)
	trimmed = []

	for index, message in enumerate(messages):
		role = message.get("role")
		has_tool_calls = role == "assistant" and bool(message.get("tool_calls"))

		if has_tool_calls and index != latest_tool_call_index:
			content = message.get("content")
			if isinstance(content, str) and content:
				trimmed.append({"role": "assistant", "content": content})
			continue

		if role == "tool":
			if latest_tool_call_index is None or index <= latest_tool_call_index:
				continue

		trimmed.append(copy.deepcopy(message))

	return trimmed


def _keep_latest_image(messages, compact_screenshot_messages):
	kept_latest_image = False

	for index in range(len(messages) - 1, -1, -1):
		content = messages[index].get("content")
		if not isinstance(content, list):
			continue

		sanitized_content = []
		removed_image = False
		for item in reversed(content):
			if item.get("type") == "image_url":
				if not kept_latest_image:
					sanitized_content.append(item)
					kept_latest_image = True
				else:
					removed_image = True
			else:
				sanitized_content.append(item)

		restored_content = list(reversed(sanitized_content))
		if (
			removed_image
			and compact_screenshot_messages
			and _is_refresh_screenshot_message(restored_content)
		):
			messages.pop(index)
		else:
			compacted_content = _compacted_screenshot_content(restored_content)
			if removed_image and compact_screenshot_messages and compacted_content is not None:
				messages[index]["content"] = compacted_content
			else:
				messages[index]["content"] = restored_content


def _latest_tool_call_index(messages):
	for index in range(len(messages) - 1, -1, -1):
		message = messages[index]
		if message.get("role") == "assistant" and message.get("tool_calls"):
			return index
	return None


def _is_refresh_screenshot_message(content):
	if len(content) != 1:
		return False
	item = content[0]
	if item.get("type") != "text":
		return False
	text = item.get("text")
	return isinstance(text, str) and text.strip().startswith("Latest screenshot.")


def _compacted_screenshot_content(content):
	if len(content) != 1:
		return None
	item = content[0]
	if item.get("type") != "text":
		return None
	text = item.get("text")
	if not isinstance(text, str):
		return None

	marker = "\n\nLatest screenshot."
	marker_index = text.find(marker)
	if marker_index == -1:
		return None

	prefix = text[:marker_index]
	if not prefix.startswith("Previous tool result:"):
		return None

	text_item = copy.deepcopy(item)
	text_item["text"] = prefix
	return [text_item]
