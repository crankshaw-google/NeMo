

def fake_initialize_model_parallel(
    world_size,
    rank,
    tensor_model_parallel_size_,
    pipeline_model_parallel_size_,
    pipeline_model_parallel_split_rank_=None,
    virtual_pipeline_model_parallel_size_=None,
):
    # TODO TODO TODO(crankshaw): Update this
    """
    Fake initialize model data parallel groups so that we can instantiate model parallel models before DDP is initialized.
    This is needed because PTL execution flow is init model, init trainer -> call trainer.fit(model). DDP is initialized during .fit.
    This function is taken from megatron.core.parallel_state and modified so that the distributed groups are not created.
    We only need the tensor parallel and pipeline parallel ranks to instantiate the model.

    Arguments:
        tensor_model_parallel_size: number of GPUs used to parallelize model tensor.
        pipeline_model_parallel_size: number of GPUs used to parallelize model pipeline.

    Let's say we have a total of 16 GPUs denoted by g0 ... g15 and we
    use 2 GPUs to parallelize the model tensor, and 4 GPUs to parallelize
    the model pipeline. The present function will
    create 8 tensor model-parallel groups, 4 pipeline model-parallel groups
    and 8 data-parallel groups as:
        8 data_parallel groups:
            [g0, g2], [g1, g3], [g4, g6], [g5, g7], [g8, g10], [g9, g11], [g12, g14], [g13, g15]
        8 tensor model-parallel groups:
            [g0, g1], [g2, g3], [g4, g5], [g6, g7], [g8, g9], [g10, g11], [g12, g13], [g14, g15]
        4 pipeline model-parallel groups:
            [g0, g4, g8, g12], [g1, g5, g9, g13], [g2, g6, g10, g14], [g3, g7, g11, g15]
    Note that for efficiency, the caller should make sure adjacent ranks
    are on the same DGX box. For example if we are using 2 DGX-1 boxes
    with a total of 16 GPUs, rank 0 to 7 belong to the first box and
    ranks 8 to 15 belong to the second box.
    """

    # Get world size and rank. Ensure some consistencies.
    tensor_model_parallel_size = min(tensor_model_parallel_size_, world_size)
    pipeline_model_parallel_size = min(pipeline_model_parallel_size_, world_size)
    model_parallel_size = tensor_model_parallel_size * pipeline_model_parallel_size

    assert (
        world_size % tensor_model_parallel_size * pipeline_model_parallel_size == 0
    ), f'world_size: {world_size} must be divisible by tensor_model_parallel_size: {tensor_model_parallel_size} times pipeline_model_parallel_size {pipeline_model_parallel_size}'
    data_parallel_size = world_size // (tensor_model_parallel_size * pipeline_model_parallel_size)

    num_tensor_model_parallel_groups = world_size // tensor_model_parallel_size
    num_pipeline_model_parallel_groups = world_size // pipeline_model_parallel_size

    virtual_pipeline_model_parallel_rank = None
    if virtual_pipeline_model_parallel_size_ is not None:
        virtual_pipeline_model_parallel_rank = 0

    # Build the data-parallel groups.
    all_data_parallel_group_ranks = []
    for i in range(pipeline_model_parallel_size):
        start_rank = i * num_pipeline_model_parallel_groups
        end_rank = (i + 1) * num_pipeline_model_parallel_groups
        for j in range(tensor_model_parallel_size):
            ranks = range(start_rank + j, end_rank, tensor_model_parallel_size)
            all_data_parallel_group_ranks.append(list(ranks))
            if rank in ranks:
                data_parallel_group = list(ranks)
                print(f'Rank {rank} has data parallel group: {data_parallel_group}')

    data_parallel_rank = data_parallel_group.index(rank)
    print(f'All data parallel group ranks: {all_data_parallel_group_ranks}')
    print(f'Ranks {rank} has data parallel rank: {data_parallel_rank}')

    # Build the model-parallel groups.
    all_model_parallel_group_ranks = []
    for i in range(data_parallel_size):
        ranks = [data_parallel_group_ranks[i] for data_parallel_group_ranks in all_data_parallel_group_ranks]
        all_model_parallel_group_ranks.append(ranks)
        if rank in ranks:
            print(f'Rank {rank} has model parallel group: {list(ranks)}')
    print(f'All model parallel group ranks: {all_model_parallel_group_ranks}')

    # Build the tensor model-parallel groups.
    all_tensor_model_parallel_group_ranks = []
    tensor_model_parallel_group = None
    for i in range(num_tensor_model_parallel_groups):
        ranks = range(i * tensor_model_parallel_size, (i + 1) * tensor_model_parallel_size)
        all_tensor_model_parallel_group_ranks.append(list(ranks))
        if rank in ranks:
            tensor_model_parallel_group = list(ranks)
            print(f'Rank {rank} has tensor model parallel group: {tensor_model_parallel_group}')

    tensor_model_parallel_rank = tensor_model_parallel_group.index(rank)

    print(f'All tensor model parallel group ranks: {all_tensor_model_parallel_group_ranks}')
    print(f'Rank {rank} has tensor model parallel rank: {tensor_model_parallel_rank}')

    # Build the pipeline model-parallel groups and embedding groups
    # (first and last rank in each pipeline model-parallel group).
    all_pipeline_model_parallel_group_ranks = []
    all_embedding_group_ranks = []
    pipeline_model_parallel_group = None
    embedding_group = None
    embedding_rank = None
    for i in range(num_pipeline_model_parallel_groups):
        ranks = range(i, world_size, num_pipeline_model_parallel_groups)
        all_pipeline_model_parallel_group_ranks.append(list(ranks))
        if rank in ranks:
            pipeline_model_parallel_group = list(ranks)
            print(f'Rank {rank} has pipeline model parallel group: {pipeline_model_parallel_group}')

        # Setup embedding group (to exchange gradients between
        # first and last stages).
        if len(ranks) > 1:
            embedding_ranks = [ranks[0], ranks[-1]]
            all_embedding_group_ranks.append(embedding_ranks)
        else:
            embedding_ranks = ranks
            all_embedding_group_ranks.append(list(embedding_ranks))
        if rank in embedding_ranks:
            embedding_group = list(embedding_ranks)
            print(f'Rank {rank} has embedding group: {embedding_group}')

    pipeline_model_parallel_rank = pipeline_model_parallel_group.index(rank)
    if embedding_group is not None:
        embedding_rank = embedding_group.index(rank)

    print(f'All pipeline model parallel group ranks: {all_pipeline_model_parallel_group_ranks}')
    print(f'Rank {rank} has pipeline model parallel rank {pipeline_model_parallel_rank}')
    print(f'All embedding group ranks: {all_pipeline_model_parallel_group_ranks}')
    print(f'Rank {rank} has embedding rank: {embedding_rank}')

    return (
        tensor_model_parallel_rank,
        pipeline_model_parallel_rank,
        model_parallel_size,
        data_parallel_size,
        pipeline_model_parallel_split_rank_,
        virtual_pipeline_model_parallel_rank,
    )

if __name__ == "__main__":
    world_size = 5*8
    rank = 0
    tensor_model_parallel_size_ = 8
    pipeline_model_parallel_size_ = 5
    pipeline_model_parallel_split_rank_=None
    virtual_pipeline_model_parallel_size_=None
    print(f"{world_size=}\n{rank=}\n{tensor_model_parallel_size_=}\n{pipeline_model_parallel_size_=}\n\n")
    fake_initialize_model_parallel(
        world_size,
        rank,
        tensor_model_parallel_size_,
        pipeline_model_parallel_size_,
        pipeline_model_parallel_split_rank_=None,
        virtual_pipeline_model_parallel_size_=None,
    )
