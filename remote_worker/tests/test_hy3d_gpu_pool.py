import asyncio

from hy3d_gpu_pool import GpuSlotPool


def test_pool_hands_out_one_slot_per_gpu() -> None:
    pool = GpuSlotPool(["0", "1"], copies=1)

    async def scenario() -> None:
        first = await pool.acquire()
        second = await pool.acquire()
        assert {first, second} == {"0", "1"}
        waiter = asyncio.create_task(pool.acquire())
        await asyncio.sleep(0)
        assert not waiter.done()
        pool.release(first)
        assert await asyncio.wait_for(waiter, timeout=1) == first

    asyncio.run(scenario())


def test_pool_hands_out_two_slots_on_one_gpu() -> None:
    pool = GpuSlotPool(["0"], copies=2)

    async def scenario() -> None:
        first = await pool.acquire()
        second = await pool.acquire()
        assert [first, second] == ["0", "0"]
        waiter = asyncio.create_task(pool.acquire())
        await asyncio.sleep(0)
        assert not waiter.done()
        pool.release(first)
        assert await asyncio.wait_for(waiter, timeout=1) == "0"

    asyncio.run(scenario())
