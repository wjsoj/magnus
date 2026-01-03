# back_end/python_scripts/tests/test_services/test_vlm_inference.py
import asyncio
from pywheels import get_answer_async, run_tasks_concurrently_async


async def main():
    
    N = 1000
    
    async def _get_answer_async(
        prompt: str,
        model: str,
    )-> str:
        return await get_answer_async(
            prompt = prompt,
            model = model,
            images = ["pictures/dog.png"],
            image_placeholder = "<image>",
            trial_num = 9999,
            trial_interval = 1,
            max_completion_tokens = 2000, # 防止模型胡言乱语
        )
    
    get_answer_results = await run_tasks_concurrently_async(
        task = _get_answer_async,
        task_indexers = list(range(N)),
        task_inputs = [(
            "简单描述一下这张图片 <image> 里有啥",
            "Qwen2-VL-2B",
        )] * N,
    )
    
    response = get_answer_results[N - 1]
    print(response)


if __name__ == "__main__":
    
    asyncio.run(main())